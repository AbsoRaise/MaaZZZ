from __future__ import annotations

import json
import re
import shutil
import time
from functools import lru_cache
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
    write_json,
)
from backend.service.disk_metadata import DiskMetadataStore


ProgressCallback = Callable[[dict[str, Any]], None]
CancelCallback = Callable[[], bool]


class ScanCancelled(RuntimeError):
    pass


class MaaRuntime(Protocol):
    def connect(self, profile: dict[str, Any]) -> dict[str, Any]:
        ...

    def run_task(self, entry: str, profile: dict[str, Any]) -> dict[str, Any]:
        ...

    def scan_visible_grid(
        self,
        profile: dict[str, Any],
        cancel_requested: CancelCallback | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
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
        if not self.tasker.bind(self.resource, self.controller):
            raise RuntimeError("Maa Tasker 绑定资源或控制器失败")
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

    def scan_visible_grid(
        self,
        profile: dict[str, Any],
        cancel_requested: CancelCallback | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        strategy = _scan_strategy(profile)
        if strategy in {"row_major_template", "template_row_major"}:
            return self._scan_visible_grid_row_major(profile)
        return self._scan_visible_grid_legacy(profile)

    def _scan_visible_grid_legacy(self, profile: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        if self.tasker is None or self.controller is None:
            raise RuntimeError("Maa Tasker 尚未初始化")

        from maa.pipeline import JOCR, JRecognitionType, JTemplateMatch

        maa_config = _dict_or_empty(profile.get("maa"))
        grid = _dict_or_empty(maa_config.get("visible_grid"))
        rows = int(grid.get("rows") or 0)
        columns = int(grid.get("columns") or 0)
        scan_rows = int(grid.get("scan_rows") or rows)
        max_scan_rows = int(grid.get("max_scan_rows") or 400)
        auto_scroll_trigger_row = int(grid.get("auto_scroll_trigger_row") or rows)
        stable_selected_row = int(grid.get("stable_selected_row") or max(1, rows - 1))
        first = grid.get("first_cell_center")
        gap = grid.get("cell_gap")
        if rows <= 0 or columns <= 0 or not _is_pair(first) or not _is_pair(gap):
            raise ValueError("maa.visible_grid 需要 rows/columns/first_cell_center/cell_gap")

        detail_roi = _rect_or_default(maa_config.get("detail_ocr_roi"), [1380, 258, 470, 540])
        scan_page = int(maa_config.get("scan_page") or 1)
        actions = _dict_or_empty(profile.get("actions"))
        click_delay = float(actions.get("detail_open_delay_ms") or 120) / 1000
        auto_scroll_delay = float(actions.get("auto_scroll_delay_ms") or max(180, int(click_delay * 1000))) / 1000
        auto_scroll_settle_delay = float(actions.get("auto_scroll_settle_delay_ms") or 200) / 1000
        selected_retry_delay = float(actions.get("selected_retry_delay_ms") or 80) / 1000
        max_consecutive_unknown_cells = int(actions.get("max_consecutive_unknown_cells") or (columns + 3))
        match_config = _dict_or_empty(grid.get("template_match"))
        grid_roi = _rect_or_default(match_config.get("roi"), [70, 160, 1280, 790])
        scroll_change_threshold = float(actions.get("scroll_change_threshold") or 2.3)
        detail_change_threshold = float(actions.get("detail_change_threshold") or 3.0)
        disks: list[dict[str, Any]] = []
        logs: list[str] = _LiveLogList(self.debug_dir / "latest_logs.txt")
        logs.append("scanner_stop_rules=v2 inferred_zero_score_enabled=true")
        cached_grid_cells: list[dict[str, Any]] | None = None
        cached_empty_cells: list[dict[str, Any]] | None = None
        consecutive_unknown_cells = 0

        def check_cancel() -> None:
            if cancel_requested is not None and cancel_requested():
                logs.append("用户请求中止扫描")
                raise ScanCancelled("扫描已中止")

        def describe_cell(cell: dict[str, Any] | None) -> str:
            if not cell:
                return "none"
            return (
                f"row={cell.get('row')},col={cell.get('column')},"
                f"score={float(cell.get('score') or 0):.3f},source={cell.get('source')},"
                f"x={cell.get('x')},y={cell.get('y')}"
            )

        def refresh_cells() -> None:
            check_cancel()
            nonlocal cached_grid_cells, cached_empty_cells
            cached_grid_cells = self._detect_visible_grid_cells(profile, rows, columns)
            cached_empty_cells = self._detect_empty_grid_cells(profile, rows, columns)
            if cached_grid_cells:
                logs.append(f"Maa 模板匹配识别到 {len(cached_grid_cells)} 个可见驱动盘格子")
            else:
                logs.append("Maa 模板匹配未识别到可用格子，回退到配置坐标")

        def capture_grid_snapshot() -> Any:
            check_cancel()
            self.controller.post_screencap().wait()
            return _image_roi_copy(self.controller.cached_image, _scale_roi(grid_roi, profile, self.controller.cached_image))

        def mark_unknown(reason: str) -> str:
            nonlocal consecutive_unknown_cells
            logs.append(reason)
            consecutive_unknown_cells += 1
            if consecutive_unknown_cells >= max_consecutive_unknown_cells:
                logs.append(
                    f"连续 {consecutive_unknown_cells} 个格子未识别到可信详情，"
                    "为避免无限扫描，判定当前扫描结束"
                )
                return "empty"
            return "unknown"

        def click_and_read(row: int, visual_row: int, column: int, delay: float) -> str:
            check_cancel()
            nonlocal cached_grid_cells, cached_empty_cells, consecutive_unknown_cells
            if cached_grid_cells is None:
                refresh_cells()
            matched_cell = _cell_by_row_column(cached_grid_cells, visual_row, column)
            empty_cell = _cell_by_row_column(cached_empty_cells, visual_row, column)
            stop_reason = _empty_stop_reason(cached_empty_cells, cached_grid_cells, visual_row, column)
            logs.append(
                f"template decision logical_row={row} visual_row={visual_row} column={column}: "
                f"disk={describe_cell(matched_cell)} empty={describe_cell(empty_cell)} "
                f"stop_reason={stop_reason or 'none'}"
            )
            if stop_reason is not None:
                logs.append(f"第 {row} 行第 {column} 个为空位，扫描结束")
                return "empty"
            x = int(first[0] + (column - 1) * gap[0])
            y = int(first[1] + (visual_row - 1) * gap[1])
            click_source = "fallback"
            if matched_cell is not None:
                x = matched_cell["x"]
                y = matched_cell["y"]
                click_source = str(matched_cell.get("source") or "template")
            elif self.controller.cached_image is not None:
                x, y = _scale_point_to_image(x, y, profile, self.controller.cached_image)

            logs.append(
                f"准备点击 logical_row={row} visual_row={visual_row} column={column} "
                f"target=({x},{y}) source={click_source} matched={describe_cell(matched_cell)} "
                f"empty={describe_cell(empty_cell)}"
            )

            try:
                self.controller.post_screencap().wait()
                before_image = self.controller.cached_image
                before_detail = _image_roi_copy(before_image, _scale_roi(detail_roi, profile, before_image))
                self.controller.post_click(x, y).wait()
                time.sleep(delay)
                check_cancel()
                self.controller.post_screencap().wait()
                image = self.controller.cached_image
                scaled_roi = _scale_roi(detail_roi, profile, image)
                after_detail = _image_roi_copy(image, scaled_roi)
                detail_delta = _mean_abs_image_delta(before_detail, after_detail)
                job = self.tasker.post_recognition(
                    JRecognitionType.OCR,
                    JOCR(roi=scaled_roi),
                    image,
                )
                job.wait()
                disk = parse_detail_ocr_results(
                    self._ocr_results_from_task(job.get()),
                    inventory_pos={
                        "page": scan_page,
                        "row": row,
                        "column": column,
                        "index": (row - 1) * columns + column,
                    },
                )
            except Exception as exc:
                logs.append(f"跳过第 {row} 行第 {column} 个：点击/识别失败：{exc}")
                return "error"

            if disk is None:
                return mark_unknown(f"跳过第 {row} 行第 {column} 个：未识别到驱动盘详情")

            if not _should_accept_detail_after_click(
                detail_delta=detail_delta,
                detail_change_threshold=detail_change_threshold,
                matched_cell=matched_cell,
            ):
                return mark_unknown(
                    f"跳过第 {row} 行第 {column} 个：详情区域变化过小 "
                    f"delta={detail_delta:.3f} <= {detail_change_threshold:.3f}，"
                    "且当前格子没有明确驱动盘模板命中，疑似空位保留上一块详情"
                )

            disks.append(validate_disk(disk))
            consecutive_unknown_cells = 0
            logs.append(
                f"识别第 {row} 行第 {column} 个（可见第 {visual_row} 行，{click_source}，"
                f"detail_delta={detail_delta:.3f}）：{disk['set_name']} [{disk['slot']}]"
            )
            return "disk"

        logical_row = 1
        check_cancel()
        refresh_cells()
        for visual_row in range(1, min(auto_scroll_trigger_row, rows + 1)):
            for column in range(1, columns + 1):
                check_cancel()
                if click_and_read(logical_row, visual_row, column, click_delay) == "empty":
                    return disks, logs
            logical_row += 1

        while logical_row <= max_scan_rows:
            check_cancel()
            logs.append(f"点击底行第 {logical_row} 行第 1 个，判断是否继续下滑")
            grid_before_click = capture_grid_snapshot()
            status = click_and_read(logical_row, auto_scroll_trigger_row, 1, auto_scroll_delay)
            if status == "empty":
                break

            logs.append(
                f"底行第 {logical_row} 行第 1 个点击完成，等待 {auto_scroll_settle_delay:.2f}s 后重新识别当前选中格"
            )
            time.sleep(auto_scroll_settle_delay)
            check_cancel()
            grid_after_click = capture_grid_snapshot()
            scroll_delta = _mean_abs_image_delta(grid_before_click, grid_after_click)
            selected_cell = self._detect_selected_grid_cell(profile, rows, columns, expected_column=1)
            selected_row = int(selected_cell.get("row") or 0) if selected_cell else 0
            logs.append(
                f"bottom-row click scroll_delta={scroll_delta:.3f}, "
                f"threshold={scroll_change_threshold:.3f}, selected={describe_cell(selected_cell)}"
            )
            logs.append(f"底行点击后重新识别当前选中格: {describe_cell(selected_cell)}")
            if _reached_bottom_after_bottom_click(
                scroll_delta=scroll_delta,
                scroll_change_threshold=scroll_change_threshold,
                selected_row=selected_row,
                auto_scroll_trigger_row=auto_scroll_trigger_row,
                stable_selected_row=stable_selected_row,
            ):
                logs.append(f"第 {logical_row} 行第 1 个点击后仍选中第 {auto_scroll_trigger_row} 行，判定已到最后一行")
                for column in range(2, columns + 1):
                    if click_and_read(logical_row, auto_scroll_trigger_row, column, click_delay) == "empty":
                        return disks, logs
                break

            cached_grid_cells = None
            cached_empty_cells = None
            selected_summary = describe_cell(selected_cell)
            for attempt in range(2):
                if selected_row == stable_selected_row:
                    break
                logs.append(
                    f"滚动后选中检测[{attempt + 1}/2]: {selected_summary}; "
                    f"expected_row={stable_selected_row}, fallback_row={stable_selected_row}"
                )
                time.sleep(selected_retry_delay)
                check_cancel()
                selected_cell = self._detect_selected_grid_cell(profile, rows, columns, expected_column=1)
                selected_row = int(selected_cell.get("row") or 0) if selected_cell else 0
                selected_summary = describe_cell(selected_cell)
            if selected_row != stable_selected_row:
                logs.append(
                    f"滚动后选中行异常: selected={selected_summary}; "
                    f"using fallback_row={stable_selected_row} for continuation"
                )
                selected_row = stable_selected_row
                selected_summary = f"fallback row={stable_selected_row}"

            continuation_row = selected_row or stable_selected_row
            logs.append(
                f"底行点击后当前选中={selected_summary}; "
                f"继续识别逻辑行={logical_row} 的剩余驱动盘，下一行使用 visual_row={continuation_row}"
            )
            refresh_cells()
            for column in range(2, columns + 1):
                check_cancel()
                logs.append(
                    f"继续扫描下一列: logical_row={logical_row}, visual_row={continuation_row}, "
                    f"next_column={column}, selected={selected_summary}"
                )
                if click_and_read(logical_row, continuation_row, column, click_delay) == "empty":
                    return disks, logs
            logical_row += 1
            cached_grid_cells = None
            cached_empty_cells = None

        if logical_row > max_scan_rows:
            logs.append(f"已达到最大扫描行数 {max_scan_rows}，停止扫描")

        return disks, logs

    def _scan_visible_grid_row_major(self, profile: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        if self.tasker is None or self.controller is None:
            raise RuntimeError("Maa Tasker is not initialized")

        from maa.pipeline import JOCR, JRecognitionType

        maa_config = _dict_or_empty(profile.get("maa"))
        grid = _dict_or_empty(maa_config.get("visible_grid"))
        strategy_config = _dict_or_empty(grid.get("row_major_template"))
        rows = int(grid.get("rows") or 0)
        columns = int(grid.get("columns") or 0)
        max_scan_rows = int(grid.get("max_scan_rows") or 400)
        auto_scroll_trigger_row = int(grid.get("auto_scroll_trigger_row") or rows)
        stable_selected_row = int(grid.get("stable_selected_row") or max(1, rows - 1))
        first = grid.get("first_cell_center")
        gap = grid.get("cell_gap")
        if rows <= 0 or columns <= 0 or not _is_pair(first) or not _is_pair(gap):
            raise ValueError("maa.visible_grid requires rows/columns/first_cell_center/cell_gap")

        detail_roi = _rect_or_default(maa_config.get("detail_ocr_roi"), [1380, 258, 470, 540])
        scan_page = int(maa_config.get("scan_page") or 1)
        actions = _dict_or_empty(profile.get("actions"))
        click_delay = float(actions.get("detail_open_delay_ms") or 120) / 1000
        auto_scroll_delay = float(actions.get("auto_scroll_delay_ms") or max(180, int(click_delay * 1000))) / 1000
        auto_scroll_settle_delay = float(actions.get("auto_scroll_settle_delay_ms") or 200) / 1000
        selected_retry_delay = float(actions.get("selected_retry_delay_ms") or 80) / 1000
        selected_retries = max(1, int(strategy_config.get("selected_retries") or 3))
        max_consecutive_unknown_cells = int(actions.get("max_consecutive_unknown_cells") or (columns + 3))
        match_config = _dict_or_empty(grid.get("template_match"))
        grid_roi = _rect_or_default(match_config.get("roi"), [70, 160, 1280, 790])
        scroll_change_threshold = float(actions.get("scroll_change_threshold") or 2.3)
        detail_change_threshold = float(actions.get("detail_change_threshold") or 3.0)
        disks: list[dict[str, Any]] = []
        logs: list[str] = _LiveLogList(self.debug_dir / "latest_logs.txt")
        logs.append("scanner_strategy=row_major_template_v1")
        cached_grid_cells: list[dict[str, Any]] | None = None
        cached_empty_cells: list[dict[str, Any]] | None = None
        consecutive_unknown_cells = 0

        def describe_cell(cell: dict[str, Any] | None) -> str:
            if not cell:
                return "none"
            return (
                f"row={cell.get('row')},col={cell.get('column')},"
                f"score={float(cell.get('score') or 0):.3f},source={cell.get('source')},"
                f"x={cell.get('x')},y={cell.get('y')}"
            )

        def refresh_cells() -> None:
            nonlocal cached_grid_cells, cached_empty_cells
            cached_grid_cells = self._detect_visible_grid_cells(profile, rows, columns)
            cached_empty_cells = self._detect_empty_grid_cells(profile, rows, columns)
            logs.append(
                f"row_major refresh disk_cells={len(cached_grid_cells or [])} "
                f"empty_cells={len(cached_empty_cells or [])}"
            )

        def capture_grid_snapshot() -> Any:
            self.controller.post_screencap().wait()
            return _image_roi_copy(self.controller.cached_image, _scale_roi(grid_roi, profile, self.controller.cached_image))

        def detect_selected_column_one() -> dict[str, Any] | None:
            selected_cell: dict[str, Any] | None = None
            for attempt in range(1, selected_retries + 1):
                selected_cell = self._detect_selected_grid_cell(profile, rows, columns, expected_column=1)
                logs.append(f"row_major selected retry={attempt}/{selected_retries} selected={describe_cell(selected_cell)}")
                if selected_cell is not None:
                    return selected_cell
                time.sleep(selected_retry_delay)
            return selected_cell

        def mark_unknown(reason: str) -> str:
            nonlocal consecutive_unknown_cells
            logs.append(reason)
            consecutive_unknown_cells += 1
            if consecutive_unknown_cells >= max_consecutive_unknown_cells:
                logs.append(f"row_major stop: consecutive_unknown_cells={consecutive_unknown_cells}")
                return "empty"
            return "unknown"

        def click_and_read(logical_row: int, visual_row: int, column: int, delay: float) -> str:
            nonlocal cached_grid_cells, cached_empty_cells, consecutive_unknown_cells
            if cached_grid_cells is None:
                refresh_cells()
            matched_cell = _cell_by_row_column(cached_grid_cells, visual_row, column)
            empty_cell = _cell_by_row_column(cached_empty_cells, visual_row, column)
            stop_reason = _empty_stop_reason(cached_empty_cells, cached_grid_cells, visual_row, column)
            logs.append(
                f"row_major decision logical_row={logical_row} visual_row={visual_row} column={column}: "
                f"disk={describe_cell(matched_cell)} empty={describe_cell(empty_cell)} "
                f"stop_reason={stop_reason or 'none'}"
            )
            if stop_reason is not None:
                logs.append(f"row_major stop: empty at logical_row={logical_row} visual_row={visual_row} column={column}")
                return "empty"

            x = int(first[0] + (column - 1) * gap[0])
            y = int(first[1] + (visual_row - 1) * gap[1])
            click_source = "fallback"
            if matched_cell is not None:
                x = matched_cell["x"]
                y = matched_cell["y"]
                click_source = str(matched_cell.get("source") or "template")
            elif self.controller.cached_image is not None:
                x, y = _scale_point_to_image(x, y, profile, self.controller.cached_image)

            logs.append(
                f"row_major click logical_row={logical_row} visual_row={visual_row} column={column} "
                f"target=({x},{y}) source={click_source}"
            )

            try:
                self.controller.post_screencap().wait()
                before_image = self.controller.cached_image
                before_detail = _image_roi_copy(before_image, _scale_roi(detail_roi, profile, before_image))
                self.controller.post_click(x, y).wait()
                time.sleep(delay)
                self.controller.post_screencap().wait()
                image = self.controller.cached_image
                scaled_roi = _scale_roi(detail_roi, profile, image)
                after_detail = _image_roi_copy(image, scaled_roi)
                detail_delta = _mean_abs_image_delta(before_detail, after_detail)
                job = self.tasker.post_recognition(
                    JRecognitionType.OCR,
                    JOCR(roi=scaled_roi),
                    image,
                )
                job.wait()
                disk = parse_detail_ocr_results(
                    self._ocr_results_from_task(job.get()),
                    inventory_pos={
                        "page": scan_page,
                        "row": logical_row,
                        "column": column,
                        "index": (logical_row - 1) * columns + column,
                    },
                )
            except Exception as exc:
                logs.append(f"row_major skip: click/read failed logical_row={logical_row} column={column}: {exc}")
                return "error"

            if disk is None:
                return mark_unknown(f"row_major unknown: no detail logical_row={logical_row} column={column}")

            if not _should_accept_detail_after_click(
                detail_delta=detail_delta,
                detail_change_threshold=detail_change_threshold,
                matched_cell=matched_cell,
            ):
                return mark_unknown(
                    f"row_major unknown: unchanged detail logical_row={logical_row} column={column} "
                    f"delta={detail_delta:.3f} threshold={detail_change_threshold:.3f}"
                )

            disks.append(validate_disk(disk))
            consecutive_unknown_cells = 0
            logs.append(
                f"row_major recognized logical_row={logical_row} visual_row={visual_row} "
                f"column={column} source={click_source} delta={detail_delta:.3f}: "
                f"{disk['set_name']} [{disk['slot']}]"
            )
            return "disk"

        def scan_columns(logical_row: int, visual_row: int, start_column: int) -> str:
            for column in range(start_column, columns + 1):
                status = click_and_read(logical_row, visual_row, column, click_delay)
                if status == "empty":
                    return "empty"
            return "done"

        logical_row = 1
        refresh_cells()
        while logical_row <= max_scan_rows:
            if logical_row < auto_scroll_trigger_row:
                if scan_columns(logical_row, logical_row, 1) == "empty":
                    break
                logical_row += 1
                continue

            logs.append(f"row_major bottom probe logical_row={logical_row} column=1 visual_row={auto_scroll_trigger_row}")
            grid_before_click = capture_grid_snapshot()
            status = click_and_read(logical_row, auto_scroll_trigger_row, 1, auto_scroll_delay)
            if status == "empty":
                break

            time.sleep(auto_scroll_settle_delay)
            grid_after_click = capture_grid_snapshot()
            scroll_delta = _mean_abs_image_delta(grid_before_click, grid_after_click)
            selected_cell = detect_selected_column_one()
            selected_row = int(selected_cell.get("row") or 0) if selected_cell else 0
            reached_bottom = _reached_bottom_after_bottom_click(
                scroll_delta=scroll_delta,
                scroll_change_threshold=scroll_change_threshold,
                selected_row=selected_row,
                auto_scroll_trigger_row=auto_scroll_trigger_row,
                stable_selected_row=stable_selected_row,
            )
            logs.append(
                f"row_major bottom result logical_row={logical_row} scroll_delta={scroll_delta:.3f} "
                f"threshold={scroll_change_threshold:.3f} selected={describe_cell(selected_cell)} "
                f"reached_bottom={reached_bottom}"
            )

            cached_grid_cells = None
            cached_empty_cells = None
            if reached_bottom:
                refresh_cells()
                scan_columns(logical_row, auto_scroll_trigger_row, 2)
                break

            continuation_row = selected_row if selected_row > 0 else stable_selected_row
            if continuation_row != stable_selected_row:
                logs.append(
                    f"row_major abnormal selected_row={continuation_row}; "
                    f"continue with stable_selected_row={stable_selected_row}"
                )
                continuation_row = stable_selected_row
            refresh_cells()
            if scan_columns(logical_row, continuation_row, 2) == "empty":
                break
            logical_row += 1
            cached_grid_cells = None
            cached_empty_cells = None

        if logical_row > max_scan_rows:
            logs.append(f"row_major stop: max_scan_rows={max_scan_rows}")

        return disks, logs

    def _detect_visible_grid_cells(self, profile: dict[str, Any], rows: int, columns: int) -> list[dict[str, Any]]:
        if self.tasker is None or self.controller is None:
            return []

        from maa.pipeline import JRecognitionType, JTemplateMatch

        maa_config = _dict_or_empty(profile.get("maa"))
        grid = _dict_or_empty(maa_config.get("visible_grid"))
        match_config = _dict_or_empty(grid.get("template_match"))
        if not match_config.get("enabled", True):
            return []

        templates = [str(item) for item in match_config.get("templates") or [] if str(item)]
        if not templates:
            return []
        roi = _rect_or_default(match_config.get("roi"), [70, 160, 1280, 790])
        threshold = match_config.get("threshold") or [0.78 for _ in templates]
        if not isinstance(threshold, list):
            threshold = [float(threshold) for _ in templates]
        click_offset = _pair_or_default(match_config.get("click_offset"), [18, 70])
        dedupe_tolerance = _pair_or_default(match_config.get("dedupe_tolerance"), [55, 55])
        row_tolerance = int(match_config.get("row_tolerance") or 70)
        order_by = str(match_config.get("order_by") or "Vertical")
        method = int(match_config.get("method") or 5)
        green_mask = bool(match_config.get("green_mask"))
        box_coordinate_space = str(match_config.get("box_coordinate_space") or "auto")
        first = match_config.get("first_cell_center")
        if not _is_pair(first) and _is_pair(grid.get("first_cell_center")):
            grid_first = grid["first_cell_center"]
            first = [int(grid_first[0] - roi[0]), int(grid_first[1] - roi[1])]

        self.controller.post_screencap().wait()
        image = self.controller.cached_image
        scaled_roi = _scale_roi(roi, profile, image)
        scaled_first = _scale_pair_to_image(first, profile, image) if _is_pair(first) else first
        scaled_gap = _scale_pair_to_image(grid.get("cell_gap"), profile, image) if _is_pair(grid.get("cell_gap")) else grid.get("cell_gap")
        job = self.tasker.post_recognition(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(
                template=templates,
                roi=scaled_roi,
                threshold=threshold,
                order_by=order_by,
                method=method,
                green_mask=green_mask,
            ),
            image,
        )
        job.wait()
        task_detail = job.get()
        matches = self._recognition_results_from_task(task_detail)
        cells = grid_cells_from_template_matches(
            matches,
            rows=rows,
            columns=columns,
            click_offset=click_offset,
            dedupe_tolerance=dedupe_tolerance,
            row_tolerance=row_tolerance,
            first=scaled_first,
            gap=scaled_gap,
            roi=list(scaled_roi),
            box_coordinate_space=box_coordinate_space,
        )
        write_json(
            self.debug_dir / "template_grid_latest.json",
            {
                "roi": roi,
                "scaled_roi": list(scaled_roi),
                "templates": templates,
                "threshold": threshold,
                "method": method,
                "green_mask": green_mask,
                "click_offset": click_offset,
                "dedupe_tolerance": dedupe_tolerance,
                "row_tolerance": row_tolerance,
                "first_cell_center": first,
                "scaled_first_cell_center": scaled_first,
                "cell_gap": grid.get("cell_gap"),
                "scaled_cell_gap": scaled_gap,
                "coordinate_space": "image",
                "box_coordinate_space": box_coordinate_space,
                "raw_match_count": len(matches),
                "raw_matches": matches,
                "effective_roi": _effective_roi_from_cells(cells),
                "cells": cells,
            },
        )
        return cells

    def _detect_selected_grid_cell(
        self,
        profile: dict[str, Any],
        rows: int,
        columns: int,
        expected_column: int | None = None,
    ) -> dict[str, Any] | None:
        cells = self._detect_grid_cells_by_template_key(profile, rows, columns, "selected_templates")
        matched = [cell for cell in cells if cell.get("source") == "template-grid"]
        if not matched:
            return None
        if expected_column is not None:
            expected_matches = [cell for cell in matched if int(cell.get("column") or 0) == expected_column]
            if expected_matches:
                return max(expected_matches, key=lambda cell: float(cell.get("score") or 0))
            return None
        return max(matched, key=lambda cell: float(cell.get("score") or 0))

    def _detect_empty_grid_cells(self, profile: dict[str, Any], rows: int, columns: int) -> list[dict[str, Any]]:
        cells = self._detect_grid_cells_by_template_key(profile, rows, columns, "empty_templates")
        return [cell for cell in cells if cell.get("source") == "template-grid"]

    def _detect_grid_cells_by_template_key(
        self,
        profile: dict[str, Any],
        rows: int,
        columns: int,
        template_key: str,
    ) -> list[dict[str, Any]]:
        if self.tasker is None or self.controller is None:
            return []

        from maa.pipeline import JRecognitionType, JTemplateMatch

        maa_config = _dict_or_empty(profile.get("maa"))
        grid = _dict_or_empty(maa_config.get("visible_grid"))
        match_config = _dict_or_empty(grid.get("template_match"))
        templates = self._valid_template_names(match_config.get(template_key) or [])
        if not templates:
            return []

        roi = _rect_or_default(match_config.get("roi"), [70, 160, 1280, 790])
        threshold = match_config.get(f"{template_key}_threshold")
        if threshold is None:
            threshold = match_config.get("threshold") or [0.78 for _ in templates]
        if not isinstance(threshold, list):
            threshold = [float(threshold) for _ in templates]
        if len(threshold) != len(templates):
            threshold = [float(threshold[0] if threshold else 0.78) for _ in templates]
        click_offset = _pair_or_default(match_config.get("click_offset"), [62, 59])
        dedupe_tolerance = _pair_or_default(match_config.get("dedupe_tolerance"), [55, 55])
        row_tolerance = int(match_config.get("row_tolerance") or 70)
        method = int(match_config.get("method") or 5)
        green_mask = bool(match_config.get("green_mask"))
        box_coordinate_space = str(match_config.get("box_coordinate_space") or "auto")
        first = match_config.get("first_cell_center")
        if not _is_pair(first) and _is_pair(grid.get("first_cell_center")):
            grid_first = grid["first_cell_center"]
            first = [int(grid_first[0] - roi[0]), int(grid_first[1] - roi[1])]

        self.controller.post_screencap().wait()
        image = self.controller.cached_image
        scaled_roi = _scale_roi(roi, profile, image)
        job = self.tasker.post_recognition(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(
                template=templates,
                roi=scaled_roi,
                threshold=threshold,
                order_by="Vertical",
                method=method,
                green_mask=green_mask,
            ),
            image,
        )
        job.wait()
        return grid_cells_from_template_matches(
            self._recognition_results_from_task(job.get()),
            rows=rows,
            columns=columns,
            click_offset=click_offset,
            dedupe_tolerance=dedupe_tolerance,
            row_tolerance=row_tolerance,
            first=_scale_pair_to_image(first, profile, image) if _is_pair(first) else first,
            gap=_scale_pair_to_image(grid.get("cell_gap"), profile, image) if _is_pair(grid.get("cell_gap")) else grid.get("cell_gap"),
            roi=list(scaled_roi),
            box_coordinate_space=box_coordinate_space,
        )

    def _valid_template_names(self, raw_templates: Any) -> list[str]:
        names = [str(item) for item in raw_templates if str(item)] if isinstance(raw_templates, list) else []
        valid: list[str] = []
        for name in names:
            path = self.resource_root / "image" / name
            if path.exists() and path.stat().st_size > 64:
                valid.append(name)
        return valid

    def _ocr_results_from_task(self, task_detail: Any) -> list[dict[str, Any]]:
        return [item for item in self._recognition_results_from_task(task_detail) if item.get("text")]

    def _recognition_results_from_task(self, task_detail: Any) -> list[dict[str, Any]]:
        if task_detail is None or not getattr(task_detail, "node_id_list", None):
            return []
        if self.tasker is None:
            return []
        node = self.tasker.get_node_detail(task_detail.node_id_list[0])
        recognition = getattr(node, "recognition", None)
        if recognition is None:
            return []
        results = recognition.filtered_results or recognition.all_results
        return [
            {
                "text": getattr(result, "text", ""),
                "box": list(getattr(result, "box", [0, 0, 0, 0])),
                "score": float(getattr(result, "score", 0) or 0),
            }
            for result in results
            if getattr(result, "box", None) is not None
        ]

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

    def test_connection(self) -> dict[str, Any]:
        self.load_profile()
        return self.connect()

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
        row = int(pos.get("row") or 0)
        column = int(pos.get("column") or pos.get("col") or 0)
        if row <= 0 or column <= 0:
            raise ValueError("定位需要 row/column")
        x, y, visual_row = self.visible_grid_click_position(row, column)
        return {
            "supported": False,
            "message": "真实 Maa 定位尚未接入，已返回目标行列和点击坐标",
            "target": {"row": row, "column": column, "visual_row": visual_row, "x": x, "y": y},
        }

    def visible_grid_click_position(self, row: int, column: int) -> tuple[int, int, int]:
        maa_config = _dict_or_empty(self.profile.get("maa"))
        grid = _dict_or_empty(maa_config.get("visible_grid"))
        rows = int(grid.get("rows") or 0)
        columns = int(grid.get("columns") or 0)
        first = grid.get("first_cell_center")
        gap = grid.get("cell_gap")
        if rows <= 0 or columns <= 0 or not _is_pair(first) or not _is_pair(gap) or column > columns:
            x, y = self.inventory_cell_center(row, column)
            return x, y, row

        auto_scroll_trigger_row = int(grid.get("auto_scroll_trigger_row") or rows)
        stable_selected_row = int(grid.get("stable_selected_row") or max(1, rows - 1))
        if row < auto_scroll_trigger_row:
            visual_row = row
        elif column == 1:
            visual_row = auto_scroll_trigger_row
        else:
            visual_row = stable_selected_row
        visual_row = max(1, min(rows, visual_row))
        return (
            int(first[0] + (column - 1) * gap[0]),
            int(first[1] + (visual_row - 1) * gap[1]),
            visual_row,
        )

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

    def scan_inventory(
        self,
        on_progress: ProgressCallback | None = None,
        cancel_requested: CancelCallback | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        return self.run_scan(on_progress, cancel_requested)

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
        self,
        on_progress: ProgressCallback | None = None,
        cancel_requested: CancelCallback | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        logs: list[str] = []

        def check_cancel() -> None:
            if cancel_requested is not None and cancel_requested():
                logs.append("用户请求中止扫描")
                raise ScanCancelled("扫描已中止")

        def emit(progress: int, message: str) -> None:
            check_cancel()
            payload = {"progress": progress, "message": message}
            logs.append(message)
            if on_progress is not None:
                on_progress(payload)

        emit(5, "初始化 Maa 扫描配置")
        self.load_profile()
        emit(20, "检查 MaaFramework 连接状态")
        check_cancel()
        try:
            self.connect()
        except Exception as exc:
            message = str(exc)
            logs.append(message)
            write_debug_artifacts(self.debug_dir, {"error": message}, logs)
            raise
        if self.is_maa_enabled():
            if hasattr(self.runtime, "scan_visible_grid"):
                emit(35, "遍历当前可见驱动盘并识别详情")
                disks, scan_logs = self.runtime.scan_visible_grid(
                    self.profile,
                    cancel_requested=cancel_requested,
                )
                logs.extend(scan_logs)
                check_cancel()
                output_path = self.resource_root / "output" / "latest_scan.json"
                write_json(output_path, {"disks": disks})
                result = {"disk_count": len(disks), "disks": disks}
            else:
                entry = str(_dict_or_empty(self.profile.get("maa")).get("entry") or "ScanDisks")
                emit(35, f"执行 MaaFramework 任务：{entry}")
                task_result = self.runtime.run_task(entry, self.profile)
                check_cancel()
                disks = self.read_maa_output()
                result = {"disk_count": len(disks), "disks": disks, "maa_task": task_result}
            write_debug_artifacts(self.debug_dir, result, logs)
            if "maa_task" in result:
                emit(100, "MaaFramework 任务执行完成")
            else:
                emit(100, f"MaaFramework 当前页识别完成：{len(disks)} 枚")
            return disks, logs

        emit(45, "扫描当前驱动盘仓库页")
        check_cancel()
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


def _scan_strategy(profile: dict[str, Any]) -> str:
    maa_config = _dict_or_empty(profile.get("maa"))
    grid = _dict_or_empty(maa_config.get("visible_grid"))
    raw = maa_config.get("scan_strategy") or grid.get("scan_strategy") or "legacy_template"
    return str(raw).strip().lower()


class _LiveLogList(list[str]):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def append(self, item: str) -> None:
        super().append(item)
        with self.path.open("a", encoding="utf-8") as file:
            if len(self) > 1:
                file.write("\n")
            file.write(item)


def parse_detail_ocr_results(
    results: list[dict[str, Any]],
    inventory_pos: dict[str, int],
) -> dict[str, Any] | None:
    rows = sorted((_normalize_ocr_result(item) for item in results), key=lambda item: (item["y"], item["x"]))
    rows = [item for item in rows if item["text"]]
    if not rows:
        return None

    title = next((item for item in rows if re.search(r"\[[1-6]\]", item["text"])), None)
    if title is None:
        return None
    slot_match = re.search(r"\[([1-6])\]", title["text"])
    if slot_match is None:
        return None

    set_name = title["text"][: slot_match.start()].strip()
    if not set_name:
        return None

    level = _extract_level(rows)
    main_head_y = _find_label_y(rows, "主属性", default=title["y"] + 100)
    sub_head_y = _find_label_y(rows, "副属性", default=main_head_y + 55)
    stat_rows = [item for item in rows if item["y"] > main_head_y and item["text"] not in {"主属性", "副属性"}]
    main_stat = _parse_stat_line(stat_rows, main_head_y, sub_head_y)
    sub_stats = _parse_sub_stat_lines(stat_rows, sub_head_y)
    if main_stat is None:
        return None

    return {
        "slot": int(slot_match.group(1)),
        "set_name": set_name,
        "rarity": "S",
        "level": level,
        "inventory_pos": inventory_pos,
        "main_stat": main_stat,
        "sub_stats": sub_stats,
        "ocr_raw": results,
    }


def iter_grid_scan_targets(
    *,
    rows: int,
    columns: int,
    scan_rows: int,
    first: list[float] | tuple[float, float],
    gap: list[float] | tuple[float, float],
    auto_scroll_trigger_row: int,
    stable_selected_row: int,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for logical_row in range(1, scan_rows + 1):
        for column in range(1, columns + 1):
            causes_auto_scroll = False
            if logical_row < auto_scroll_trigger_row:
                visual_row = logical_row
            elif column == 1:
                visual_row = auto_scroll_trigger_row
                causes_auto_scroll = True
            else:
                visual_row = stable_selected_row

            visual_row = max(1, min(rows, visual_row))
            targets.append(
                {
                    "row": logical_row,
                    "column": column,
                    "visual_row": visual_row,
                    "x": int(first[0] + (column - 1) * gap[0]),
                    "y": int(first[1] + (visual_row - 1) * gap[1]),
                    "causes_auto_scroll": causes_auto_scroll,
                }
            )
    return targets


def grid_cells_from_template_matches(
    matches: list[dict[str, Any]],
    *,
    rows: int,
    columns: int,
    click_offset: list[int],
    dedupe_tolerance: list[int],
    row_tolerance: int,
    first: Any = None,
    gap: Any = None,
    roi: Any = None,
    box_coordinate_space: str = "auto",
) -> list[dict[str, Any]]:
    roi_rect = _roi_rect(roi)
    normalized = [_normalize_match_result(match, click_offset, roi_rect, box_coordinate_space) for match in matches]
    normalized.sort(key=lambda item: (-item["score"], item["y"], item["x"]))
    deduped: list[dict[str, Any]] = []
    tolerance_x, tolerance_y = dedupe_tolerance
    for item in normalized:
        if any(abs(item["x"] - kept["x"]) <= tolerance_x and abs(item["y"] - kept["y"]) <= tolerance_y for kept in deduped):
            continue
        deduped.append(item)

    if _is_pair(first) and _is_pair(gap):
        calibrated = _calibrated_grid_cells_from_matches(
            deduped,
            rows=rows,
            columns=columns,
            first=[float(first[0]), float(first[1])],
            gap=[float(gap[0]), float(gap[1])],
            row_tolerance=row_tolerance,
        )
        if calibrated:
            return calibrated

    grouped: list[list[dict[str, Any]]] = []
    for item in sorted(deduped, key=lambda candidate: (candidate["y"], candidate["x"])):
        row_group = next(
            (group for group in grouped if abs(item["y"] - _average([cell["y"] for cell in group])) <= row_tolerance),
            None,
        )
        if row_group is None:
            grouped.append([item])
        else:
            row_group.append(item)

    cells: list[dict[str, Any]] = []
    grouped.sort(key=lambda group: _average([cell["y"] for cell in group]))
    for row_index, group in enumerate(grouped[:rows], start=1):
        group.sort(key=lambda item: item["x"])
        for column_index, item in enumerate(group[:columns], start=1):
            cells.append({**item, "row": row_index, "column": column_index, "source": "template"})
    return cells


def _calibrated_grid_cells_from_matches(
    matches: list[dict[str, Any]],
    *,
    rows: int,
    columns: int,
    first: list[float],
    gap: list[float],
    row_tolerance: int,
) -> list[dict[str, Any]]:
    assignments: dict[tuple[int, int], dict[str, Any]] = {}
    origin_x_values: list[float] = []
    origin_y_values: list[float] = []
    col_tolerance = max(35.0, float(gap[0]) * 0.45)
    row_match_tolerance = max(float(row_tolerance), float(gap[1]) * 0.45)

    for item in matches:
        local_x = item.get("local_x", item["x"])
        local_y = item.get("local_y", item["y"])
        column = round((local_x - first[0]) / gap[0]) + 1
        row = round((local_y - first[1]) / gap[1]) + 1
        if not (1 <= row <= rows and 1 <= column <= columns):
            continue
        expected_x = first[0] + (column - 1) * gap[0]
        expected_y = first[1] + (row - 1) * gap[1]
        if abs(local_x - expected_x) > col_tolerance or abs(local_y - expected_y) > row_match_tolerance:
            continue
        key = (row, column)
        if key not in assignments or item["score"] > assignments[key]["score"]:
            assignments[key] = item
        origin_x_values.append(local_x - (column - 1) * gap[0])
        origin_y_values.append(local_y - (row - 1) * gap[1])

    if not assignments:
        return []

    origin_x = _median(origin_x_values)
    origin_y = _median(origin_y_values)
    cells: list[dict[str, Any]] = []
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            matched = assignments.get((row, column))
            cells.append(
                {
                    "row": row,
                    "column": column,
                    "local_x": int(round(origin_x + (column - 1) * gap[0])),
                    "local_y": int(round(origin_y + (row - 1) * gap[1])),
                    "x": int(round(origin_x + (column - 1) * gap[0] + matches[0].get("roi_x", 0))),
                    "y": int(round(origin_y + (row - 1) * gap[1] + matches[0].get("roi_y", 0))),
                    "score": float(matched.get("score", 0)) if matched else 0.0,
                    "box": matched.get("box") if matched else None,
                    "source": "template-grid" if matched else "template-inferred",
                }
            )
    return cells


def _cell_by_row_column(cells: list[dict[str, Any]] | None, row: int, column: int) -> dict[str, Any] | None:
    if not cells:
        return None
    return next((cell for cell in cells if cell["row"] == row and cell["column"] == column), None)


def _is_confirmed_empty_cell(
    empty_cells: list[dict[str, Any]] | None,
    disk_cells: list[dict[str, Any]] | None,
    row: int,
    column: int,
) -> bool:
    return _empty_stop_reason(empty_cells, disk_cells, row, column) is not None


def _should_stop_at_empty_or_unmatched_cell(
    empty_cells: list[dict[str, Any]] | None,
    disk_cells: list[dict[str, Any]] | None,
    row: int,
    column: int,
) -> bool:
    return _empty_stop_reason(empty_cells, disk_cells, row, column) is not None


def _empty_stop_reason(
    empty_cells: list[dict[str, Any]] | None,
    disk_cells: list[dict[str, Any]] | None,
    row: int,
    column: int,
) -> str | None:
    disk_cell = _cell_by_row_column(disk_cells, row, column)
    if disk_cell is not None and str(disk_cell.get("source") or "").strip() == "template-grid":
        return None
    empty_cell = _cell_by_row_column(empty_cells, row, column)
    if empty_cell is None:
        return None
    return "empty-template"


def _reached_bottom_after_bottom_click(
    *,
    scroll_delta: float,
    scroll_change_threshold: float,
    selected_row: int,
    auto_scroll_trigger_row: int,
    stable_selected_row: int,
) -> bool:
    if selected_row == auto_scroll_trigger_row:
        return True
    if selected_row == stable_selected_row:
        return False
    if scroll_delta <= scroll_change_threshold:
        return True
    return False


def _should_accept_detail_after_click(
    *,
    detail_delta: float,
    detail_change_threshold: float,
    matched_cell: dict[str, Any] | None,
) -> bool:
    if matched_cell is not None and str(matched_cell.get("source") or "").strip() == "template-grid":
        return True
    return detail_delta > detail_change_threshold


def _normalize_match_result(
    item: dict[str, Any],
    click_offset: list[int],
    roi_rect: list[int],
    box_coordinate_space: str,
) -> dict[str, Any]:
    box = item.get("box") or [0, 0, 0, 0]
    box = [int(value) for value in box[:4]]
    box_space = _resolve_box_coordinate_space(box, roi_rect, box_coordinate_space)
    if box_space == "screen":
        screen_x = box[0] + int(click_offset[0])
        screen_y = box[1] + int(click_offset[1])
        local_x = screen_x - roi_rect[0]
        local_y = screen_y - roi_rect[1]
    else:
        local_x = box[0] + int(click_offset[0])
        local_y = box[1] + int(click_offset[1])
        screen_x = roi_rect[0] + local_x
        screen_y = roi_rect[1] + local_y
    return {
        "box": box,
        "box_coordinate_space": box_space,
        "local_x": local_x,
        "local_y": local_y,
        "x": screen_x,
        "y": screen_y,
        "roi_x": roi_rect[0],
        "roi_y": roi_rect[1],
        "score": float(item.get("score") or 0),
    }


def _average(values: list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _roi_rect(roi: Any) -> list[int]:
    if isinstance(roi, list) and len(roi) >= 4 and all(isinstance(item, (int, float)) for item in roi[:4]):
        return [int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3])]
    if isinstance(roi, list) and len(roi) >= 2 and all(isinstance(item, (int, float)) for item in roi[:2]):
        return [int(roi[0]), int(roi[1]), 0, 0]
    return [0, 0, 0, 0]


def _resolve_box_coordinate_space(box: list[int], roi: list[int], configured: str) -> str:
    if configured in {"screen", "local"}:
        return configured
    roi_x, roi_y, roi_w, roi_h = roi
    inside_screen_roi = roi_x <= box[0] <= roi_x + roi_w and roi_y <= box[1] <= roi_y + roi_h
    plausible_local = 0 <= box[0] <= roi_w and 0 <= box[1] <= roi_h
    if inside_screen_roi and not plausible_local:
        return "screen"
    if plausible_local and not inside_screen_roi:
        return "local"
    if inside_screen_roi and plausible_local:
        return "screen" if box[0] >= roi_x and box[1] >= roi_y else "local"
    return "local"


def _effective_roi_from_cells(cells: list[dict[str, Any]]) -> list[int] | None:
    if not cells:
        return None
    xs = [int(cell["x"]) for cell in cells]
    ys = [int(cell["y"]) for cell in cells]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _normalize_ocr_result(item: dict[str, Any]) -> dict[str, Any]:
    box = item.get("box") or [0, 0, 0, 0]
    text = str(item.get("text") or "").strip().replace(" ", "")
    return {
        "text": text,
        "box": box,
        "x": int(box[0]),
        "y": int(box[1]),
        "w": int(box[2]),
        "h": int(box[3]),
        "score": float(item.get("score") or 0),
    }


def _extract_level(rows: list[dict[str, Any]]) -> int:
    for item in rows:
        match = re.search(r"(\d+)\s*/\s*(\d+)", item["text"])
        if match:
            return int(match.group(1))
    return 0


def _find_label_y(rows: list[dict[str, Any]], label: str, default: int) -> int:
    for item in rows:
        if label in item["text"]:
            return item["y"]
    return default


def _parse_stat_line(
    rows: list[dict[str, Any]],
    top_y: int,
    bottom_y: int,
) -> dict[str, Any] | None:
    candidates = [item for item in rows if top_y < item["y"] < bottom_y and _is_known_main_stat(item["text"])]
    if not candidates:
        return None
    label = min(candidates, key=lambda item: item["y"])
    value = _closest_value(rows, label)
    return {"name": _strip_stat_upgrade(label["text"])[0], "value": value or ""}


def _parse_sub_stat_lines(rows: list[dict[str, Any]], top_y: int) -> list[dict[str, Any]]:
    bottom_y = top_y + 155
    labels = [item for item in rows if top_y < item["y"] < bottom_y and _is_known_sub_stat(item["text"])]
    labels.sort(key=lambda item: (item["y"], item["x"]))
    stats: list[dict[str, Any]] = []
    for label in labels:
        name, upgrade = _strip_stat_upgrade(label["text"])
        if name in {"主属性", "副属性"} or not _is_known_sub_stat(name):
            continue
        value = _closest_value(rows, label)
        if value is None:
            continue
        extra_upgrade = _closest_upgrade(rows, label)
        stat: dict[str, Any] = {"name": name, "value": value or ""}
        if upgrade is not None or extra_upgrade is not None:
            stat["upgrade"] = upgrade if upgrade is not None else extra_upgrade
        stats.append(stat)
    return stats


def _looks_like_stat_name(text: str) -> bool:
    if not text or text in {"主属性", "副属性"}:
        return False
    if re.fullmatch(r"[+\d./%]+", text):
        return False
    if text.startswith("等级"):
        return False
    return True


@lru_cache(maxsize=2)
def _known_stat_names(kind: str) -> frozenset[str]:
    try:
        metadata = DiskMetadataStore().get_all()
    except Exception:
        metadata = {}
    key = "main_stats" if kind == "main" else "sub_stats"
    values = metadata.get(key) if isinstance(metadata, dict) else None
    return frozenset(_normalize_stat_text(item) for item in values or [] if isinstance(item, str))


def _normalize_stat_text(text: str) -> str:
    return _strip_stat_upgrade(str(text or "").strip().replace(" ", ""))[0]


def _is_known_main_stat(text: str) -> bool:
    return _normalize_stat_text(text) in _known_stat_names("main")


def _is_known_sub_stat(text: str) -> bool:
    return _normalize_stat_text(text) in _known_stat_names("sub")


def _strip_stat_upgrade(text: str) -> tuple[str, int | None]:
    match = re.search(r"\+(\d+)$", text)
    if not match:
        return text, None
    return text[: match.start()], int(match.group(1))


def _closest_value(rows: list[dict[str, Any]], label: dict[str, Any]) -> str | None:
    values = [
        item
        for item in rows
        if item["x"] > label["x"] + 120
        and abs(item["y"] - label["y"]) <= 18
        and re.search(r"\d", item["text"])
        and not item["text"].startswith("+")
    ]
    if not values:
        return None
    return min(values, key=lambda item: abs(item["y"] - label["y"]))["text"]


def _closest_upgrade(rows: list[dict[str, Any]], label: dict[str, Any]) -> int | None:
    upgrades = [
        item
        for item in rows
        if label["x"] < item["x"] <= label["x"] + 130
        and abs(item["y"] - label["y"]) <= 18
        and re.fullmatch(r"\+(\d+)", item["text"])
    ]
    if not upgrades:
        return None
    match = re.fullmatch(r"\+(\d+)", upgrades[0]["text"])
    return int(match.group(1)) if match else None


def _is_pair(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) for item in value)


def _rect_or_default(value: Any, default: list[int]) -> list[int]:
    if isinstance(value, list) and len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
        return [int(item) for item in value]
    return default


def _pair_or_default(value: Any, default: list[int]) -> list[int]:
    if _is_pair(value):
        return [int(value[0]), int(value[1])]
    return default


def _scale_roi(roi: list[int], profile: dict[str, Any], image: Any) -> tuple[int, int, int, int]:
    resolution = profile.get("resolution")
    if not _is_pair(resolution):
        return tuple(roi)  # type: ignore[return-value]
    image_height, image_width = image.shape[:2]
    scale_x = image_width / float(resolution[0])
    scale_y = image_height / float(resolution[1])
    return (
        int(roi[0] * scale_x),
        int(roi[1] * scale_y),
        int(roi[2] * scale_x),
        int(roi[3] * scale_y),
    )


def _image_roi_copy(image: Any, roi: tuple[int, int, int, int]) -> Any:
    x, y, width, height = roi
    if image is None or width <= 0 or height <= 0:
        return None
    return image[y : y + height, x : x + width].copy()


def _mean_abs_image_delta(before: Any, after: Any) -> float:
    if before is None or after is None or getattr(before, "shape", None) != getattr(after, "shape", None):
        return 999.0
    diff = before.astype("int16") - after.astype("int16")
    return float(abs(diff).mean())


def _scale_point_to_image(x: int | float, y: int | float, profile: dict[str, Any], image: Any) -> tuple[int, int]:
    resolution = profile.get("resolution")
    if not _is_pair(resolution):
        return int(x), int(y)
    image_height, image_width = image.shape[:2]
    return int(float(x) * image_width / float(resolution[0])), int(float(y) * image_height / float(resolution[1]))


def _scale_pair_to_image(value: Any, profile: dict[str, Any], image: Any) -> list[int]:
    if not _is_pair(value):
        return value
    x, y = _scale_point_to_image(value[0], value[1], profile, image)
    return [x, y]


def _scale_y_to_image(value: int | float, profile: dict[str, Any], image: Any) -> int:
    resolution = profile.get("resolution")
    if not _is_pair(resolution):
        return int(value)
    image_height = image.shape[:2][0]
    return int(float(value) * image_height / float(resolution[1]))
