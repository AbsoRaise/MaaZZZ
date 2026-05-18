from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Protocol

from backend.service.maa_profile import (
    DEFAULT_DEBUG_DIR,
    DEFAULT_PROFILE_PATH,
    RESOURCE_ROOT,
    cell_center,
    ensure_scan_resource_tree,
    load_scan_profile,
    position_from_index,
    validate_disk,
    write_debug_artifacts,
)


ProgressCallback = Callable[[dict[str, Any]], None]


class MaaRuntime(Protocol):
    def connect(self, profile: dict[str, Any]) -> dict[str, Any]:
        ...

    def run_task(self, entry: str, profile: dict[str, Any]) -> dict[str, Any]:
        ...


class MaaFrameworkRuntime:
    """Thin adapter around MaaFramework's Python binding.

    The import stays lazy so tests and placeholder mode do not require MaaFw.
    """

    def __init__(self, resource_root: Path, debug_dir: Path) -> None:
        self.resource_root = resource_root
        self.debug_dir = debug_dir
        self.resource = None
        self.controller = None
        self.tasker = None

    def connect(self, profile: dict[str, Any]) -> dict[str, Any]:
        from maa.controller import (
            DbgController,
            MaaWin32InputMethodEnum,
            MaaWin32ScreencapMethodEnum,
            Win32Controller,
        )
        from maa.resource import Resource
        from maa.tasker import Tasker
        from maa.toolkit import Toolkit

        maa_config = _dict_or_empty(profile.get("maa"))
        controller_type = str(maa_config.get("controller") or "win32").lower()
        if controller_type == "dbg":
            dbg_path = maa_config.get("dbg_path") or self.debug_dir / "latest_screenshot.png"
            dbg_path = Path(dbg_path)
            if not dbg_path.exists():
                raise FileNotFoundError(f"DbgController 截图不存在：{dbg_path}")
            self.controller = DbgController(dbg_path)
            controller_detail = {"dbg_path": str(dbg_path)}
        elif controller_type == "win32":
            hwnd = maa_config.get("hwnd") or self._find_win32_hwnd(Toolkit.find_desktop_windows(), maa_config)
            screencap = self._enum_value(
                MaaWin32ScreencapMethodEnum,
                maa_config.get("screencap") or "Background",
            )
            mouse = self._enum_value(
                MaaWin32InputMethodEnum,
                maa_config.get("mouse") or "PostMessageWithCursorPos",
            )
            keyboard = self._enum_value(
                MaaWin32InputMethodEnum,
                maa_config.get("keyboard") or "PostMessage",
            )
            self.controller = Win32Controller(hwnd, screencap, mouse, keyboard)
            controller_detail = {"hwnd": int(hwnd), "screencap": screencap.name, "mouse": mouse.name, "keyboard": keyboard.name}
        else:
            raise ValueError(f"暂未接入 Maa 控制器类型：{controller_type}")
        self.controller.post_connection().wait()

        self.resource = Resource()
        self.resource.post_bundle(self.resource_root).wait()

        self.tasker = Tasker()
        self.tasker.controller = self.controller
        self.tasker.resource = self.resource
        if not self.tasker.inited:
            raise RuntimeError("Maa Tasker 初始化失败")

        return {
            "connected": True,
            "mode": "maa",
            "controller": controller_type,
            "resource_root": str(self.resource_root),
            **controller_detail,
        }

    def run_task(self, entry: str, profile: dict[str, Any]) -> dict[str, Any]:
        if self.tasker is None:
            raise RuntimeError("Maa Tasker 尚未初始化")

        maa_config = _dict_or_empty(profile.get("maa"))
        pipeline_override = _dict_or_empty(maa_config.get("pipeline_override"))
        job = self.tasker.post_task(entry, pipeline_override)
        job.wait()
        return {
            "completed": job.done,
            "succeeded": job.succeeded,
            "entry": entry,
        }

    def _find_win32_hwnd(self, windows: list[Any], maa_config: dict[str, Any]) -> int:
        window_regex = re.compile(str(maa_config.get("window_regex") or ".*"))
        class_regex = re.compile(str(maa_config.get("class_regex") or ".*"))
        for window in windows:
            title = getattr(window, "window_name", "") or ""
            class_name = getattr(window, "class_name", "") or ""
            if window_regex.search(title) and class_regex.search(class_name):
                hwnd = getattr(window, "hwnd", None)
                hwnd_value = getattr(hwnd, "value", hwnd)
                if hwnd_value:
                    return int(hwnd_value)
        raise RuntimeError(
            "未找到匹配的绝区零窗口；请先启动游戏，或在 scan_profile.json 的 maa.hwnd 中填写窗口句柄"
        )

    def _enum_value(self, enum_type: Any, name: Any) -> Any:
        if isinstance(name, enum_type):
            return name
        try:
            return enum_type[str(name)]
        except KeyError as exc:
            valid = ", ".join(member.name for member in enum_type)
            raise ValueError(f"Maa Win32 配置值无效：{name}，可选值：{valid}") from exc


class MaaScanner:
    """MaaFramework 扫描适配层。

    目前保留可运行的模拟流程和调试工具。获得游戏截图、模板和 Pipeline 后，
    只需要把 `connect`、`scan_current_page`、`parse_disk_detail` 内部替换为真实 Maa 调用。
    """

    def __init__(
        self,
        resource_root: Path | str | None = None,
        profile_path: Path | str | None = None,
        debug_dir: Path | str | None = None,
        maa_runtime: MaaRuntime | None = None,
    ) -> None:
        self.resource_root = Path(resource_root or RESOURCE_ROOT)
        ensure_scan_resource_tree(self.resource_root)
        self.profile_path = Path(profile_path or self.resource_root / "config" / DEFAULT_PROFILE_PATH.name)
        self.debug_dir = Path(debug_dir or self.resource_root / "debug")
        self.maa_runtime = maa_runtime
        self.profile = self.load_profile()

    def load_profile(self) -> dict[str, Any]:
        self.profile = load_scan_profile(self.profile_path)
        return self.profile

    def connect(self) -> dict[str, Any]:
        if self.is_maa_enabled():
            return self.runtime.connect(self.profile)

        return {
            "connected": False,
            "mode": "placeholder",
            "message": "尚未接入真实 MaaFramework，当前使用占位扫描流程",
        }

    @property
    def runtime(self) -> MaaRuntime:
        if self.maa_runtime is None:
            self.maa_runtime = MaaFrameworkRuntime(self.resource_root, self.debug_dir)
        return self.maa_runtime

    def is_maa_enabled(self) -> bool:
        maa_config = self.profile.get("maa")
        return isinstance(maa_config, dict) and bool(maa_config.get("enabled"))

    def inventory_cell_center(self, row: int, column: int) -> tuple[int, int]:
        return cell_center(self.profile, row, column)

    def locate_disk(self, disk_or_pos: dict[str, Any]) -> dict[str, Any]:
        pos = disk_or_pos.get("inventory_pos", disk_or_pos)
        if not isinstance(pos, dict):
            raise ValueError("定位需要 inventory_pos")
        page = int(pos.get("page") or 0)
        row = int(pos.get("row") or 0)
        column = int(pos.get("column") or pos.get("col") or 0)
        if page <= 0 or row <= 0 or column <= 0:
            raise ValueError("定位需要 page/row/column")
        x, y = self.inventory_cell_center(row, column)
        # 后续自动定位会在这里执行：翻页到 page -> 点击 (x, y)。
        return {
            "supported": False,
            "message": "真实 Maa 定位尚未接入，已返回目标页和点击坐标",
            "target": {"page": page, "row": row, "column": column, "x": x, "y": y},
        }

    def scan_from_screenshot(self, image_path: Path | str) -> dict[str, Any]:
        source = Path(image_path)
        if not source.exists():
            raise FileNotFoundError(f"截图不存在：{source}")
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        latest = self.debug_dir / "latest_screenshot.png"
        shutil.copyfile(source, latest)
        result = {
            "source": str(source),
            "debug_screenshot": str(latest),
            "message": "截图已导入调试目录，等待配置 OCR/模板识别区域",
        }
        write_debug_artifacts(self.debug_dir, {"screenshot_import": result}, [result["message"]])
        return result

    def scan_inventory(self, on_progress: ProgressCallback | None = None) -> tuple[list[dict[str, Any]], list[str]]:
        return self.run_scan(on_progress)

    def scan_current_page(self, page: int = 1) -> list[dict[str, Any]]:
        # 当前返回占位数据；真实接入后这里会遍历当前页网格并读取详情。
        samples = [
            self.parse_disk_detail(page=page, index=1, slot=5, set_name="极地重金属", main_name="冰属性伤害"),
            self.parse_disk_detail(page=page, index=2, slot=4, set_name="啄木鸟电音", main_name="暴击率"),
        ]
        return [validate_disk(sample) for sample in samples]

    def parse_disk_detail(
        self,
        page: int,
        index: int,
        slot: int,
        set_name: str,
        main_name: str,
    ) -> dict[str, Any]:
        pos = position_from_index(self.profile, page=page, index=index)
        return {
            "slot": slot,
            "set_name": set_name,
            "level": 1,
            "inventory_pos": {
                "page": pos["page"],
                "row": pos["row"],
                "column": pos["column"],
                "index": pos["index"],
            },
            "main_stat": {"name": main_name, "value": 7.2},
            "sub_stats": [
                {"name": "暴击率", "value": 2.4},
                {"name": "暴击伤害", "value": 4.8},
            ],
        }

    def run_scan(
        self, on_progress: ProgressCallback | None = None
    ) -> tuple[list[dict[str, Any]], list[str]]:
        logs: list[str] = []

        def emit(progress: int, message: str) -> None:
            payload = {"progress": progress, "message": message}
            logs.append(message)
            if on_progress is not None:
                on_progress(payload)

        emit(5, "初始化 Maa 扫描配置")
        self.load_profile()
        emit(20, "检查 MaaFramework 连接状态")
        self.connect()
        if self.is_maa_enabled():
            entry = str(_dict_or_empty(self.profile.get("maa")).get("entry") or "ScanDisks")
            emit(35, f"执行 MaaFramework 任务：{entry}")
            task_result = self.runtime.run_task(entry, self.profile)
            disks = self.read_maa_output()
            result = {"disk_count": len(disks), "disks": disks, "maa_task": task_result}
            write_debug_artifacts(self.debug_dir, result, logs)
            emit(100, "MaaFramework 任务执行完成")
            return disks, logs

        emit(45, "扫描当前驱动盘仓库页")
        disks = self.scan_current_page(page=1)
        emit(80, "校验并整理驱动盘识别结果")
        result = {"disk_count": len(disks), "disks": disks}
        write_debug_artifacts(self.debug_dir, result, logs)
        emit(100, "Maa 占位扫描完成")
        return disks, logs

    def read_maa_output(self) -> list[dict[str, Any]]:
        output_path = self.resource_root / "output" / "latest_scan.json"
        if not output_path.exists():
            return []
        try:
            raw = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Maa 扫描输出 JSON 损坏：{output_path}") from exc
        disks = raw.get("disks") if isinstance(raw, dict) else raw
        if not isinstance(disks, list):
            raise ValueError("Maa 扫描输出必须是列表或包含 disks 的对象")
        return [validate_disk(dict(disk)) for disk in disks if isinstance(disk, dict)]


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
