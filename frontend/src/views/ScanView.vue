<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { diskIconFor } from '../diskIcons';

const DISK_PLACEHOLDER_ASSET = '';
const DEFAULT_METADATA = {
  disk_types: ['极地重金属', '啄木鸟电音', '震星迪斯科', '激素朋克', '獠牙重金属', '河豚电音', '自由蓝调'],
  main_stats: ['生命值', '攻击力', '防御力', '暴击率', '暴击伤害', '异常精通', '穿透率', '能量自动回复', '冲击力', '冰属性伤害'],
  sub_stats: ['生命值', '攻击力', '防御力', '暴击率', '暴击伤害', '异常精通', '穿透值'],
  rarities: ['S', 'A', 'B'],
  slots: ['1', '2', '3', '4', '5', '6'],
};
const DEFAULT_WEIGHTS = {
  暴击率: 1.2,
  暴击伤害: 1,
  攻击力: 0.8,
  '攻击力%': 0.8,
  穿透值: 0.45,
  冰属性伤害: 1,
};

const fallbackDisks = [
  {
    id: 'mock-alpha',
    name: '啄木鸟电音 5号位',
    set_name: '震星迪斯科',
    rarity: 'S',
    level: 15,
    slot: 5,
    main_stat: { name: '冲击力', value: 18 },
    sub_stats: [
      { name: '暴击率', value: 2.4, upgrade_count: 1 },
      { name: '攻击力', value: 38, upgrade_count: 0 },
    ],
    inventory_pos: { page: 1, row: 2, col: 3 },
  },
  {
    id: 'mock-beta',
    name: '激素朋克 4号位',
    set_name: '獠牙重金属',
    rarity: 'A',
    level: 12,
    slot: 4,
    main_stat: { name: '异常精通', value: 30 },
    sub_stats: [
      { name: '暴击伤害', value: 4.8, upgrade_count: 2 },
      { name: '穿透值', value: 18, upgrade_count: 0 },
    ],
    inventory_pos: { page: 1, row: 3, col: 1 },
  },
  {
    id: 'mock-gamma',
    name: '河豚电音 6号位',
    set_name: '自由蓝调',
    rarity: 'A',
    level: 9,
    slot: 6,
    main_stat: { name: '攻击力', value: 30 },
    sub_stats: [
      { name: '暴击率', value: 2.4, upgrade_count: 0 },
      { name: '暴击伤害', value: 4.8, upgrade_count: 1 },
    ],
    inventory_pos: { page: 2, row: 1, col: 4 },
  },
];

const fallbackHistory = [
  {
    scan_id: 'mock-20260518-001',
    created_at: '2026-05-18 12:30',
    disk_count: fallbackDisks.length,
    summary: '降级演示扫描',
  },
];

const isScanning = ref(false);
const progress = ref(0);
const logs = ref([]);
const currentDisks = ref([]);
const history = ref([]);
const selectedScan = ref(null);
const selectedScanDisks = ref([]);
const lastError = ref('');
const metadata = ref(DEFAULT_METADATA);
const characterBuilds = ref({});
const currentPage = ref(1);
const pageSize = 12;
const historyPage = ref(1);
const historyPageSize = 8;
const filters = ref({
  diskType: '',
  rarity: '',
  slot: '',
  stat: '',
});

const currentSummary = computed(() => {
  const total = currentDisks.value.length;
  const bySet = currentDisks.value.reduce((acc, disk) => {
    const setName = disk.set_name || disk.set || '未知套装';
    acc[setName] = (acc[setName] || 0) + 1;
    return acc;
  }, {});

  return {
    total,
    sets: Object.entries(bySet).map(([name, count]) => ({ name, count })),
  };
});

const visibleDisks = computed(() => (selectedScan.value ? selectedScanDisks.value : currentDisks.value));
const filteredDisks = computed(() => {
  return visibleDisks.value.filter((disk) => {
    if (filters.value.diskType && setNameOf(disk) !== filters.value.diskType) return false;
    if (filters.value.rarity && rarityOf(disk) !== filters.value.rarity) return false;
    if (filters.value.slot && String(disk?.slot || '') !== filters.value.slot) return false;
    if (filters.value.stat && !diskHasStat(disk, filters.value.stat)) return false;
    return true;
  });
});
const totalPages = computed(() => Math.max(1, Math.ceil(filteredDisks.value.length / pageSize)));
const displayPage = computed(() => Math.min(currentPage.value, totalPages.value));
const pagedDisks = computed(() => {
  const start = (displayPage.value - 1) * pageSize;
  return filteredDisks.value.slice(start, start + pageSize);
});
const historyTotalPages = computed(() => Math.max(1, Math.ceil(history.value.length / historyPageSize)));
const historyDisplayPage = computed(() => Math.min(historyPage.value, historyTotalPages.value));
const pagedHistory = computed(() => {
  const start = (historyDisplayPage.value - 1) * historyPageSize;
  return history.value.slice(start, start + historyPageSize);
});
const statOptions = computed(() => {
  const values = new Set([...(metadata.value.main_stats || []), ...(metadata.value.sub_stats || [])]);
  visibleDisks.value.forEach((disk) => {
    const main = statName(disk.main_stat || disk.main);
    if (main && main !== '-') values.add(main);
    subStatsOf(disk).forEach((sub) => values.add(statName(sub)));
  });
  return [...values].filter(Boolean).sort((a, b) => a.localeCompare(b, 'zh-CN'));
});
const diskTypeOptions = computed(() => {
  const values = new Set(metadata.value.disk_types || []);
  visibleDisks.value.forEach((disk) => values.add(setNameOf(disk)));
  return [...values].filter(Boolean).sort((a, b) => a.localeCompare(b, 'zh-CN'));
});

function getApi() {
  return window?.pywebview?.api || null;
}

function waitForApi(timeoutMs = 3000) {
  const existing = getApi();
  if (existing) return Promise.resolve(existing);

  return new Promise((resolve) => {
    let settled = false;
    const startedAt = Date.now();

    const finish = (api) => {
      if (settled) return;
      settled = true;
      window.removeEventListener('pywebviewready', handleReady);
      resolve(api || null);
    };

    const handleReady = () => finish(getApi());

    const poll = () => {
      const api = getApi();
      if (api || Date.now() - startedAt >= timeoutMs) {
        finish(api);
        return;
      }
      window.setTimeout(poll, 80);
    };

    window.addEventListener('pywebviewready', handleReady, { once: true });
    poll();
  });
}

function isEnvelope(response) {
  return (
    response &&
    typeof response === 'object' &&
    Object.prototype.hasOwnProperty.call(response, 'success') &&
    (Object.prototype.hasOwnProperty.call(response, 'data') || Object.prototype.hasOwnProperty.call(response, 'error'))
  );
}

function unwrapResponse(response) {
  if (!isEnvelope(response)) return response;

  if (response.success === false) {
    throw new Error(response.error || '后端操作失败');
  }

  if (response.success === true) {
    return response.data;
  }

  return response;
}

function errorMessageOf(error) {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  if (error?.error) return error.error;
  if (error?.message) return error.message;
  return '未知错误';
}

function addLog(message) {
  const stamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  logs.value = [`[${stamp}] ${message}`, ...logs.value].slice(0, 80);
}

function normalizeDisks(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.disks)) return payload.disks;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}

function scanIdOf(item) {
  return item?.scan_id || item?.id || item?.scanId || '';
}

function diskIdOf(disk, index) {
  return disk?.id || disk?.disk_id || `${disk?.name || 'disk'}-${index}`;
}

function inventoryLabel(pos) {
  if (!pos) return '第 - 行 / 第 - 个';
  const row = pos.row ?? pos.r ?? pos[1] ?? '-';
  const col = pos.column ?? pos.col ?? pos.c ?? pos[2] ?? '-';
  return `第 ${row} 行 / 第 ${col} 个`;
}

function statName(statValue) {
  if (statValue && typeof statValue === 'object') return statValue.name || statValue.stat_name || '-';
  return statValue || '-';
}

function statValue(statValue) {
  if (statValue && typeof statValue === 'object') return statValue.value ?? '-';
  return '-';
}

function statUpgradeCount(statValue) {
  if (!statValue || typeof statValue !== 'object') return 0;
  return Number(statValue.upgrade ?? 0) || 0;
}

function subStatsOf(disk) {
  return Array.isArray(disk?.sub_stats) ? disk.sub_stats : [];
}

function setNameOf(disk) {
  return disk?.set_name || disk?.set || '未知套装';
}

function rarityOf(disk) {
  return String(disk?.rarity || disk?.rank || 'A').toUpperCase();
}

function rarityClass(disk) {
  const rarity = rarityOf(disk);
  if (rarity === 'S') return 'disk-rarity-s';
  if (rarity === 'B') return 'disk-rarity-b';
  return 'disk-rarity-a';
}

function levelClass(disk) {
  const rarity = rarityOf(disk);
  if (rarity === 'S') return 'text-[#f6ce00]';
  if (rarity === 'B') return 'text-sky-300';
  return 'text-purple-300';
}

function normalizeWeights(raw) {
  if (!raw || typeof raw !== 'object') return {};
  return Object.fromEntries(Object.entries(raw).map(([key, value]) => [key, Number(value) || 0]));
}

function diskHasStat(disk, stat) {
  return statName(disk?.main_stat || disk?.main) === stat || subStatsOf(disk).some((sub) => statName(sub) === stat);
}

function resetFilters() {
  filters.value = { diskType: '', rarity: '', slot: '', stat: '' };
  currentPage.value = 1;
}

function changePage(delta) {
  currentPage.value = Math.min(totalPages.value, Math.max(1, displayPage.value + delta));
}

function changeHistoryPage(delta) {
  historyPage.value = Math.min(historyTotalPages.value, Math.max(1, historyDisplayPage.value + delta));
}

function setIconFor(disk) {
  const key = disk?.set_name || disk?.set || disk?.set_id;
  return key ? diskIconFor(key) : '';
}

function placeholderStyle(disk) {
  const asset = disk?.asset || disk?.image || disk?.icon || setIconFor(disk) || DISK_PLACEHOLDER_ASSET;
  const fallbackBackground =
    'radial-gradient(circle at 50% 50%, #f6ce00 0 7%, #09090b 8% 13%, #52525b 14% 15%, #18181b 16% 31%, #71717a 32% 33%, #09090b 34% 52%, #3f3f46 53% 54%, #18181b 55% 100%)';
  if (asset) {
    return {
      backgroundImage: `url("${asset}"), ${fallbackBackground}`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
    };
  }

  return {
    background: fallbackBackground,
  };
}

async function callApi(name, ...args) {
  const api = getApi();
  if (api?.[name]) {
    return unwrapResponse(await api[name](...args));
  }

  if (name === 'start_maa_scan') {
    throw new Error('未连接到后端窗口，无法启动 Maa 扫描；请使用桌面窗口启动项目。');
  }

  return unwrapResponse(await mockApi(name, ...args));
}

async function mockApi(name, scanId) {
  await new Promise((resolve) => window.setTimeout(resolve, 120));

  if (name === 'start_maa_scan') {
    throw new Error('未连接到后端窗口，无法启动 Maa 扫描；请使用桌面窗口启动项目。');
  }

  if (name === 'get_current_disks') return { disks: fallbackDisks };
  if (name === 'get_disk_metadata') return DEFAULT_METADATA;
  if (name === 'get_character_builds') return { 默认角色: { weights: DEFAULT_WEIGHTS } };
  if (name === 'get_scan_history') return fallbackHistory;
  if (name === 'get_scan_result') return { scan_id: scanId, disks: fallbackDisks };
  if (name === 'delete_scan_result') return { ok: true };
  if (name === 'use_scan_result') return { disks: fallbackDisks };
  if (name === 'locate_disk') {
    return {
      supported: false,
      message: '真实 Maa 定位尚未接入，当前仅返回目标仓库位置。',
      target: scanId?.inventory_pos || scanId,
    };
  }
  return null;
}

function eventPayload(event) {
  return unwrapResponse(event?.detail ?? event);
}

function handleProgress(event) {
  try {
    const payload = eventPayload(event);
    progress.value = Number(payload?.progress ?? payload?.percent ?? progress.value);
    addLog(payload?.message || `扫描进度 ${progress.value}%`);
  } catch (error) {
    handleError({ detail: { message: errorMessageOf(error) } });
  }
}

async function handleComplete(event) {
  try {
    const payload = eventPayload(event);
    isScanning.value = false;
    progress.value = 100;
    addLog(payload?.message || '扫描完成。');

    if (Array.isArray(payload?.disks)) {
      currentDisks.value = payload.disks;
    }

    await refreshCurrentDisks();
    await refreshHistory();
  } catch (error) {
    handleError({ detail: { message: errorMessageOf(error) } });
  }
}

function handleError(event) {
  const rawPayload = event?.detail ?? event;
  const payload = isEnvelope(rawPayload) && rawPayload.success === false ? rawPayload : rawPayload;
  isScanning.value = false;
  lastError.value = payload?.message || payload?.error || errorMessageOf(payload) || '扫描失败';
  addLog(`错误：${lastError.value}`);
}

async function startScan() {
  lastError.value = '';
  selectedScan.value = null;
  selectedScanDisks.value = [];
  currentPage.value = 1;
  progress.value = 0;
  logs.value = [];
  isScanning.value = true;
  addLog('启动扫描任务。');
  addLog('提示：扫描不会自动切到游戏前台，但会在后台控制绝区零窗口；扫描期间请不要手动点击仓库。');

  try {
    await callApi('start_maa_scan');
  } catch (error) {
    handleError({ detail: { message: errorMessageOf(error) } });
  }
}

async function refreshCurrentDisks() {
  try {
    currentDisks.value = normalizeDisks(await callApi('get_current_disks'));
  } catch (error) {
    lastError.value = errorMessageOf(error);
    addLog(`读取当前盘池失败：${lastError.value}`);
  }
}

async function refreshMetadata() {
  try {
    metadata.value = { ...DEFAULT_METADATA, ...(await callApi('get_disk_metadata')) };
  } catch (error) {
    addLog(`读取枚举配置失败：${errorMessageOf(error)}`);
  }
}

async function refreshCharacterBuilds() {
  try {
    characterBuilds.value = await callApi('get_character_builds');
  } catch (error) {
    characterBuilds.value = { 默认角色: { weights: DEFAULT_WEIGHTS } };
    addLog(`读取角色权重失败：${errorMessageOf(error)}`);
  }
}

async function refreshHistory() {
  try {
    const result = await callApi('get_scan_history');
    history.value = Array.isArray(result) ? result : result?.history || [];
    historyPage.value = Math.min(historyPage.value, Math.max(1, Math.ceil(history.value.length / historyPageSize)));
  } catch (error) {
    lastError.value = errorMessageOf(error);
    addLog(`读取扫描历史失败：${lastError.value}`);
  }
}

async function loadScanResult(item) {
  const scanId = scanIdOf(item);
  if (!scanId) return;

  try {
    selectedScan.value = item;
    currentPage.value = 1;
    const result = await callApi('get_scan_result', scanId);
    selectedScanDisks.value = normalizeDisks(result);
    addLog(`载入历史 ${scanId}。`);
  } catch (error) {
    lastError.value = errorMessageOf(error);
    addLog(`载入历史失败：${lastError.value}`);
  }
}

async function deleteScanResult(item) {
  const scanId = scanIdOf(item);
  if (!scanId) return;

  try {
    const result = await callApi('delete_scan_result', scanId);
    if (result === false || result?.ok === false) {
      throw new Error(result?.error || '扫描记录不存在或已被删除');
    }
    addLog(`删除历史 ${scanId}。`);
    if (scanIdOf(selectedScan.value) === scanId) {
      selectedScan.value = null;
      selectedScanDisks.value = [];
    }
    await refreshHistory();
  } catch (error) {
    lastError.value = errorMessageOf(error);
    addLog(`删除历史失败：${lastError.value}`);
  }
}

async function useScanResult(item) {
  const scanId = scanIdOf(item);
  if (!scanId) return;

  try {
    const result = await callApi('use_scan_result', scanId);
    if (result?.ok === false) {
      throw new Error(result.error || '使用历史失败');
    }
    const disks = normalizeDisks(result);
    if (Array.isArray(result) || Array.isArray(result?.disks) || Array.isArray(result?.items)) {
      currentDisks.value = disks;
    } else {
      await refreshCurrentDisks();
    }
    selectedScan.value = null;
    selectedScanDisks.value = [];
    currentPage.value = 1;
    addLog(`已将历史 ${scanId} 设为当前盘池。`);
  } catch (error) {
    lastError.value = errorMessageOf(error);
    addLog(`使用历史失败：${lastError.value}`);
  }
}

async function locateDisk(disk) {
  try {
    const result = await callApi('locate_disk', disk);
    const target = result?.target || {};
    addLog(`${result?.message || '定位预览已生成'}：第 ${target.row ?? '-'} 行 / 第 ${target.column ?? '-'} 个`);
  } catch (error) {
    lastError.value = errorMessageOf(error);
    addLog(`定位预览失败：${lastError.value}`);
  }
}

onMounted(async () => {
  window.addEventListener('maa-progress', handleProgress);
  window.addEventListener('maa-complete', handleComplete);
  window.addEventListener('maa-error', handleError);
  await waitForApi();
  await Promise.all([refreshCurrentDisks(), refreshHistory(), refreshMetadata(), refreshCharacterBuilds()]);
  addLog(getApi() ? '后端已连接。' : '后端未连接，页面使用演示数据。');
});

onBeforeUnmount(() => {
  window.removeEventListener('maa-progress', handleProgress);
  window.removeEventListener('maa-complete', handleComplete);
  window.removeEventListener('maa-error', handleError);
});
</script>

<template>
  <section class="mx-auto grid max-w-7xl gap-5 px-4 py-6 lg:grid-cols-[360px_minmax(0,1fr)]">
    <aside class="space-y-5">
      <div class="panel shadow-hard">
        <div class="panel-title">扫描控制</div>
        <div class="space-y-4 p-4">
          <button
            class="w-full rounded-sm border-4 border-[#f6ce00] bg-[#f6ce00] px-5 py-4 text-left font-mono text-sm font-black uppercase text-zinc-950 transition duration-100 hover:-translate-y-1 hover:bg-zinc-950 hover:text-[#f6ce00] active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            :disabled="isScanning"
            @click="startScan"
          >
            {{ isScanning ? '扫描中...' : '启动扫描' }}
          </button>

          <p v-if="isScanning" class="border-l-4 border-[#f6ce00] bg-zinc-950 p-3 font-mono text-xs font-black text-zinc-200">
            扫描会在后台控制绝区零窗口，不会自动切到前台；请保持仓库界面打开，扫描期间不要手动点击。
          </p>

          <div class="rounded-sm border-2 border-zinc-700 bg-zinc-950 p-3">
            <div class="mb-2 flex items-center justify-between font-mono text-xs font-black uppercase">
              <span>进度</span>
              <span class="text-[#f6ce00]">{{ Math.round(progress) }}%</span>
            </div>
            <div class="h-4 border-2 border-zinc-600 bg-zinc-900">
              <div class="h-full bg-[#f6ce00] transition-all duration-150" :style="{ width: `${Math.min(progress, 100)}%` }"></div>
            </div>
          </div>

          <div class="grid grid-cols-1 gap-3">
            <div class="rounded-sm border-2 border-zinc-700 bg-zinc-950 p-3">
              <p class="font-mono text-[10px] font-black text-zinc-500">当前盘池</p>
              <p class="mt-1 font-mono text-sm font-black text-[#f6ce00]">{{ currentSummary.total }} 枚</p>
            </div>
          </div>

          <p v-if="lastError" class="border-l-4 border-red-500 bg-red-950/40 p-3 font-mono text-xs font-black text-red-200">
            {{ lastError }}
          </p>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">当前盘池</div>
        <div class="space-y-2 p-4">
          <div class="flex items-end justify-between border-b-2 border-zinc-800 pb-3">
            <span class="font-black text-zinc-300">驱动盘总数</span>
            <span class="font-mono text-3xl font-black text-[#f6ce00]">{{ currentSummary.total }}</span>
          </div>
          <div v-if="currentSummary.sets.length" class="space-y-2">
            <div
              v-for="set in currentSummary.sets"
              :key="set.name"
              class="flex items-center justify-between rounded-sm border-2 border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-xs font-black"
            >
              <span class="truncate">{{ set.name }}</span>
              <span class="text-[#f6ce00]">{{ set.count }}</span>
            </div>
          </div>
          <p v-else class="font-mono text-xs font-bold text-zinc-500">暂无盘池数据。</p>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">扫描日志</div>
        <div class="max-h-72 space-y-2 overflow-auto p-4">
          <p v-if="!logs.length" class="font-mono text-xs font-bold text-zinc-500">等待扫描信号。</p>
          <p
            v-for="line in logs"
            :key="line"
            class="border-l-2 border-[#f6ce00] bg-zinc-950 px-3 py-2 font-mono text-xs font-bold text-zinc-300"
          >
            {{ line }}
          </p>
        </div>
      </div>
    </aside>

    <div class="space-y-5">
      <div class="panel">
        <div class="panel-title flex items-center justify-between gap-3">
          <span>{{ selectedScan ? '历史详情' : '驱动盘列表' }}</span>
          <span class="text-zinc-400">{{ filteredDisks.length }} / {{ visibleDisks.length }} 枚</span>
          <button v-if="selectedScan" class="hard-button py-1" type="button" @click="selectedScan = null; selectedScanDisks = []">
            返回当前
          </button>
        </div>
        <div class="grid gap-3 border-b-4 border-zinc-800 p-4 md:grid-cols-5">
          <label class="block">
            <span class="field-label">驱动盘类型</span>
            <select v-model="filters.diskType" class="hard-input mt-2 w-full">
              <option value="">全部</option>
              <option v-for="item in diskTypeOptions" :key="item" :value="item">{{ item }}</option>
            </select>
          </label>
          <label class="block">
            <span class="field-label">稀有度</span>
            <select v-model="filters.rarity" class="hard-input mt-2 w-full">
              <option value="">全部</option>
              <option v-for="item in metadata.rarities" :key="item" :value="item">{{ item }} 级</option>
            </select>
          </label>
          <label class="block">
            <span class="field-label">位置</span>
            <select v-model="filters.slot" class="hard-input mt-2 w-full">
              <option value="">全部</option>
              <option v-for="item in metadata.slots" :key="item" :value="item">{{ item }} 号位</option>
            </select>
          </label>
          <label class="block">
            <span class="field-label">词条</span>
            <select v-model="filters.stat" class="hard-input mt-2 w-full">
              <option value="">全部</option>
              <option v-for="item in statOptions" :key="item" :value="item">{{ item }}</option>
            </select>
          </label>
          <div class="flex items-end">
            <button class="hard-button w-full" type="button" @click="resetFilters">重置筛选</button>
          </div>
        </div>
        <div
          v-if="filteredDisks.length"
          class="flex flex-wrap items-center justify-between gap-3 border-b-4 border-zinc-800 p-4 font-mono text-xs font-black"
        >
          <span class="text-zinc-400">第 {{ displayPage }} / {{ totalPages }} 页，每页 {{ pageSize }} 枚</span>
          <div class="flex gap-2">
            <button class="hard-button py-1" type="button" :disabled="displayPage <= 1" @click="changePage(-1)">上一页</button>
            <button class="hard-button py-1" type="button" :disabled="displayPage >= totalPages" @click="changePage(1)">下一页</button>
          </div>
        </div>
        <div class="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="(disk, index) in pagedDisks"
            :key="diskIdOf(disk, index)"
            class="group rounded-sm border-4 bg-zinc-950 p-3 transition duration-100 hover:-translate-y-1"
            :class="rarityClass(disk)"
          >
            <div class="flex gap-3">
              <div class="h-20 w-20 shrink-0 rounded-sm border-4 border-zinc-800" :style="placeholderStyle(disk)"></div>
              <div class="min-w-0 flex-1">
                <div class="flex items-center justify-between gap-2">
                  <p class="truncate font-black text-zinc-100">
                    {{ setNameOf(disk) }}
                    <span class="font-mono" :class="levelClass(disk)">+{{ disk.level ?? disk.upgrade_level ?? 0 }}</span>
                  </p>
                  <span class="rounded-sm border-2 px-2 py-0.5 font-mono text-xs font-black" :class="levelClass(disk)">
                    {{ rarityOf(disk) }}
                  </span>
                </div>
                <p class="mt-1 truncate font-mono text-xs font-black text-zinc-300">
                  {{ disk.slot || '-' }} 号位驱动盘
                </p>
                <p class="mt-3 font-mono text-xs font-bold text-zinc-400">
                  仓库：{{ inventoryLabel(disk.inventory_pos) }}
                </p>
              </div>
            </div>
            <div class="mt-3 grid grid-cols-2 gap-2 border-t-2 border-zinc-800 pt-3 font-mono text-xs font-black">
              <span class="text-zinc-500">主词条</span>
              <span class="truncate text-right text-zinc-200">{{ statName(disk.main_stat || disk.main) }} {{ statValue(disk.main_stat || disk.main) }}</span>
            </div>
            <div class="mt-3 border-t-2 border-zinc-800 pt-3">
              <p class="mb-2 font-mono text-xs font-black text-zinc-500">副词条</p>
              <div v-if="subStatsOf(disk).length" class="grid grid-cols-2 gap-2">
                <span
                  v-for="sub in subStatsOf(disk)"
                  :key="`${statName(sub)}-${statValue(sub)}`"
                  class="rounded-sm border-2 border-zinc-800 bg-zinc-900 px-2 py-1 font-mono text-[11px] font-black text-zinc-300"
                >
                  {{ statName(sub) }} {{ statValue(sub) }}
                  <span class="text-[#f6ce00]">· +{{ statUpgradeCount(sub) }}</span>
                </span>
              </div>
              <p v-else class="font-mono text-xs font-bold text-zinc-600">暂无副词条</p>
            </div>
            <button
              class="mt-3 w-full rounded-sm border-2 border-zinc-700 px-3 py-2 font-mono text-xs font-black text-zinc-300 transition duration-100 hover:border-[#f6ce00] hover:bg-[#f6ce00] hover:text-zinc-950"
              type="button"
              @click="locateDisk(disk)"
            >
              定位到游戏中（预留）
            </button>
          </article>
          <div v-if="!filteredDisks.length" class="col-span-full border-4 border-dashed border-zinc-700 bg-zinc-950 p-8 text-center">
            <p class="font-mono text-sm font-black text-zinc-500">{{ visibleDisks.length ? '没有符合筛选条件的驱动盘' : '暂无驱动盘数据' }}</p>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title flex items-center justify-between gap-3">
          <span>扫描历史</span>
          <span class="text-zinc-400">{{ history.length }} 条</span>
        </div>
        <div
          v-if="history.length"
          class="flex flex-wrap items-center justify-between gap-3 border-b-4 border-zinc-800 p-4 font-mono text-xs font-black"
        >
          <span class="text-zinc-400">第 {{ historyDisplayPage }} / {{ historyTotalPages }} 页，每页 {{ historyPageSize }} 条</span>
          <div class="flex gap-2">
            <button class="hard-button py-1" type="button" :disabled="historyDisplayPage <= 1" @click="changeHistoryPage(-1)">上一页</button>
            <button class="hard-button py-1" type="button" :disabled="historyDisplayPage >= historyTotalPages" @click="changeHistoryPage(1)">下一页</button>
          </div>
        </div>
        <div class="divide-y-2 divide-zinc-800">
          <div
            v-for="item in pagedHistory"
            :key="scanIdOf(item)"
            class="grid gap-3 p-4 md:grid-cols-[minmax(0,1fr)_auto]"
          >
            <button class="text-left" type="button" @click="loadScanResult(item)">
              <p class="font-mono text-sm font-black text-[#f6ce00]">{{ scanIdOf(item) }}</p>
              <p class="mt-1 font-mono text-xs font-bold text-zinc-400">
                {{ item.created_at || item.createdAt || '未知时间' }} · {{ item.disk_count ?? item.count ?? '-' }} 枚 · {{ item.summary || '历史扫描' }}
              </p>
            </button>
            <div class="flex flex-wrap gap-2">
              <button class="hard-button" type="button" @click="loadScanResult(item)">详情</button>
              <button class="hard-button" type="button" @click="useScanResult(item)">使用</button>
              <button class="hard-button border-red-500 hover:border-red-400 hover:text-red-300" type="button" @click="deleteScanResult(item)">
                删除
              </button>
            </div>
          </div>
          <div v-if="!history.length" class="p-6 font-mono text-xs font-bold text-zinc-500">暂无历史扫描。</div>
        </div>
      </div>
    </div>
  </section>
</template>
