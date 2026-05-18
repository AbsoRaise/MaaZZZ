<script setup>
import { computed, onMounted, ref, watch } from 'vue';

const DISK_PLACEHOLDER_ASSET = '';
const STAT_ICON_ASSETS = {};
const SET_ICON_ASSETS = {};
const DEFAULT_METADATA = {
  main_stats: [
    '生命值',
    '攻击力',
    '防御力',
    '暴击率',
    '暴击伤害',
    '异常精通',
    '穿透率',
    '能量自动回复',
    '冲击力',
    '物理伤害',
    '火属性伤害',
    '冰属性伤害',
    '电属性伤害',
    '以太伤害',
    '异常掌控',
  ],
};

const defaultBuilds = {
  '艾莲·乔': {
    weights: {
      暴击率: 1.2,
      暴击伤害: 1,
      攻击力: 0.85,
      穿透值: 0.45,
    },
    preferred_main_stats: {
      4: ['暴击率', '暴击伤害'],
      5: ['冰属性伤害', '攻击力'],
      6: ['攻击力'],
    },
    preferred_sets: {
      target_set_4: '极地重金属',
      target_set_2: '啄木鸟电音',
      alternatives: [],
    },
  },
  '安比·德玛拉': {
    weights: {
      冲击力: 1.25,
      攻击力: 0.75,
      暴击率: 0.65,
      异常精通: 0.35,
    },
    preferred_main_stats: {
      4: ['暴击率'],
      5: ['电属性伤害', '攻击力'],
      6: ['冲击力'],
    },
    preferred_sets: {
      target_set_4: '震星迪斯科',
      target_set_2: '啄木鸟电音',
      alternatives: [],
    },
  },
};

const mockDisks = [
  disk('mock-1', 1, '极地重金属', '生命值', 2200, 15, 'P1-R1-C1', [
    stat('暴击率', 2.4),
    stat('攻击力', 38),
  ]),
  disk('mock-2', 2, '极地重金属', '攻击力', 316, 15, 'P1-R1-C2', [
    stat('暴击伤害', 4.8),
    stat('穿透值', 18),
  ]),
  disk('mock-3', 3, '极地重金属', '防御力', 184, 15, 'P1-R1-C3', [
    stat('暴击率', 2.4),
    stat('攻击力', 19),
  ]),
  disk('mock-4', 4, '极地重金属', '暴击率', 24, 12, 'P1-R2-C1', [
    stat('暴击伤害', 9.6),
    stat('攻击力', 38),
  ]),
  disk('mock-5', 5, '啄木鸟电音', '冰属性伤害', 30, 9, 'P1-R2-C2', [
    stat('暴击率', 4.8),
    stat('穿透值', 18),
  ]),
  disk('mock-6', 6, '啄木鸟电音', '攻击力', 30, 6, 'P1-R2-C3', [
    stat('暴击伤害', 9.6),
    stat('攻击力', 19),
  ]),
  disk('mock-7', 4, '震星迪斯科', '冲击力', 18, 0, 'P2-R1-C1', [
    stat('冲击力', 6),
    stat('攻击力', 38),
  ]),
  disk('mock-8', 6, '激素朋克', '能量自动回复', 18, 3, 'P2-R1-C2', [
    stat('暴击率', 2.4),
    stat('攻击力', 19),
  ]),
];

function stat(name, value) {
  return { name, value };
}

function disk(id, slot, setName, mainName, mainValue, level, warehouseLocation, subStats) {
  return {
    id,
    slot,
    set_name: setName,
    level,
    warehouse_location: warehouseLocation,
    main_stat: { name: mainName, value: mainValue },
    sub_stats: subStats,
  };
}

const apiReady = ref(false);
const isLoading = ref(false);
const isSaving = ref(false);
const isOptimizing = ref(false);
const isFindingPromising = ref(false);
const errorText = ref('');
const infoText = ref('');
const builds = ref({});
const metadata = ref(DEFAULT_METADATA);
const currentDisks = ref([]);
const selectedCharacter = ref('');
const draft = ref(createEmptyDraft());
const overrideConfig = ref(createOverrideConfig());
const advisorOptions = ref({
  min_effective_sub_stats: 1,
  high_weight_threshold: 0.8,
});
const optimizeResult = ref(null);
const promisingResults = ref([]);

const characterNames = computed(() => Object.keys(builds.value));
const selectedBuild = computed(() => builds.value[selectedCharacter.value] || null);
const canRun = computed(() => Boolean(selectedCharacter.value) && currentDisks.value.length > 0);
const currentSetNames = computed(() => {
  const names = new Set();
  currentDisks.value.forEach((item) => {
    const setName = item?.set_name || item?.set;
    if (setName) names.add(setName);
  });
  Object.values(builds.value).forEach((build) => {
    const sets = build?.preferred_sets || {};
    if (sets.target_set_4) names.add(sets.target_set_4);
    if (sets.target_set_2) names.add(sets.target_set_2);
  });
  return [...names].sort((a, b) => a.localeCompare(b, 'zh-CN'));
});
const diskSummary = computed(() => {
  const slots = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0 };
  const sets = {};
  currentDisks.value.forEach((item) => {
    if (slots[item?.slot] !== undefined) slots[item.slot] += 1;
    const setName = item?.set_name || item?.set || '未知套装';
    sets[setName] = (sets[setName] || 0) + 1;
  });
  return { slots, sets };
});
const mainStatOptions = computed(() => metadata.value.main_stats || DEFAULT_METADATA.main_stats);

watch(selectedCharacter, (name) => {
  loadDraftFromBuild(builds.value[name]);
  optimizeResult.value = null;
  promisingResults.value = [];
});

function createEmptyDraft() {
  return {
    weights: [{ name: '', value: 1 }],
    preferred_main_stats: {
      4: [],
      5: [],
      6: [],
    },
    preferred_sets: {
      target_set_4: '',
      target_set_2: '',
      alternatives: [],
    },
  };
}

function createOverrideConfig() {
  return {
    target_set_4: '',
    target_set_2: '',
    preferred_main_stats: {
      4: [],
      5: [],
      6: [],
    },
  };
}

function getApi() {
  return window?.pywebview?.api || null;
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
  if (response.success === false) throw new Error(response.error || '后端操作失败');
  return response.data;
}

function errorMessageOf(error) {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  if (error?.error) return error.error;
  if (error?.message) return error.message;
  return '未知错误';
}

async function callApi(name, ...args) {
  const api = getApi();
  if (api?.[name]) {
    apiReady.value = true;
    return unwrapResponse(await api[name](...args));
  }

  apiReady.value = false;
  return unwrapResponse(await mockApi(name, ...args));
}

async function mockApi(name, ...args) {
  await new Promise((resolve) => window.setTimeout(resolve, 120));
  if (name === 'get_character_builds') return structuredClone(defaultBuilds);
  if (name === 'save_character_build') {
    const [characterName, config] = args;
    defaultBuilds[characterName] = normalizeConfig(config);
    return structuredClone(defaultBuilds[characterName]);
  }
  if (name === 'get_current_disks') return structuredClone(mockDisks);
  if (name === 'get_disk_metadata') return structuredClone(DEFAULT_METADATA);
  if (name === 'get_optimize_combo') return buildMockOptimizeResult(args[0], args[1]);
  if (name === 'get_promising_disks') return buildMockPromisingResults(args[0], args[1]);
  if (name === 'locate_disk') {
    const disk = args[0] || {};
    return {
      supported: false,
      message: '真实 Maa 定位尚未接入，当前仅返回目标仓库位置。',
      target: disk.inventory_pos || disk,
    };
  }
  return null;
}

function structuredClone(value) {
  return JSON.parse(JSON.stringify(value));
}

async function loadInitialData() {
  isLoading.value = true;
  errorText.value = '';
  try {
    const [buildPayload, diskPayload] = await Promise.all([
      callApi('get_character_builds'),
      callApi('get_current_disks'),
    ]);
    builds.value = normalizeBuilds(buildPayload);
    currentDisks.value = normalizeDisks(diskPayload);
    selectedCharacter.value = characterNames.value[0] || '';
    loadDraftFromBuild(selectedBuild.value);
    infoText.value = apiReady.value ? '后端数据已加载。' : '后端未连接，当前使用演示数据。';
    metadata.value = { ...DEFAULT_METADATA, ...(await callApi('get_disk_metadata')) };
  } catch (error) {
    errorText.value = errorMessageOf(error);
  } finally {
    isLoading.value = false;
  }
}

function normalizeBuilds(payload) {
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) return payload;
  return structuredClone(defaultBuilds);
}

function normalizeDisks(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.disks)) return payload.disks;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}

function normalizeConfig(config) {
  const existingAlternatives = config?.preferred_sets?.alternatives;
  return {
    weights: normalizeWeights(config?.weights),
    preferred_main_stats: normalizePreferredMainStats(config?.preferred_main_stats),
    preferred_sets: {
      target_set_4: String(config?.preferred_sets?.target_set_4 || ''),
      target_set_2: String(config?.preferred_sets?.target_set_2 || ''),
      alternatives: Array.isArray(existingAlternatives) ? structuredClone(existingAlternatives) : [],
    },
  };
}

function normalizeWeights(weights) {
  if (!weights || typeof weights !== 'object') return {};
  return Object.fromEntries(
    Object.entries(weights)
      .filter(([key]) => String(key).trim())
      .map(([key, value]) => [String(key).trim(), Number(value) || 0]),
  );
}

function normalizePreferredMainStats(raw) {
  const result = {};
  [4, 5, 6].forEach((slot) => {
    const value = raw?.[slot] ?? raw?.[String(slot)] ?? [];
    const values = Array.isArray(value) ? value : String(value || '').split(/[，,]/);
    const stats = values.map((item) => String(item).trim()).filter(Boolean);
    if (stats.length) result[String(slot)] = stats;
  });
  return result;
}

function loadDraftFromBuild(build) {
  const normalized = normalizeConfig(build || {});
  const weightEntries = Object.entries(normalized.weights).map(([name, value]) => ({ name, value }));
  draft.value = {
    weights: weightEntries.length ? weightEntries : [{ name: '', value: 1 }],
    preferred_main_stats: {
      4: [...(normalized.preferred_main_stats['4'] || [])],
      5: [...(normalized.preferred_main_stats['5'] || [])],
      6: [...(normalized.preferred_main_stats['6'] || [])],
    },
    preferred_sets: {
      target_set_4: normalized.preferred_sets.target_set_4,
      target_set_2: normalized.preferred_sets.target_set_2,
      alternatives: normalized.preferred_sets.alternatives,
    },
  };
  overrideConfig.value = createOverrideConfig();
}

function draftToConfig() {
  return {
    weights: Object.fromEntries(
      draft.value.weights
        .map((item) => [String(item.name || '').trim(), Number(item.value) || 0])
        .filter(([name]) => name),
    ),
    preferred_main_stats: normalizePreferredMainStats(draft.value.preferred_main_stats),
    preferred_sets: {
      target_set_4: draft.value.preferred_sets.target_set_4.trim(),
      target_set_2: draft.value.preferred_sets.target_set_2.trim(),
      alternatives: Array.isArray(draft.value.preferred_sets.alternatives)
        ? structuredClone(draft.value.preferred_sets.alternatives)
        : [],
    },
  };
}

function buildRunConfig() {
  const base = draftToConfig();
  const preferredMainStats = normalizePreferredMainStats(overrideConfig.value.preferred_main_stats);
  return {
    weights: base.weights,
    preferred_sets: {
      target_set_4: overrideConfig.value.target_set_4.trim() || base.preferred_sets.target_set_4,
      target_set_2: overrideConfig.value.target_set_2.trim() || base.preferred_sets.target_set_2,
      alternatives: Array.isArray(base.preferred_sets.alternatives) ? base.preferred_sets.alternatives : [],
    },
    preferred_main_stats: Object.keys(preferredMainStats).length ? preferredMainStats : base.preferred_main_stats,
  };
}

async function saveBuild() {
  if (!selectedCharacter.value) return;
  isSaving.value = true;
  errorText.value = '';
  try {
    const config = draftToConfig();
    const saved = await callApi('save_character_build', selectedCharacter.value, config);
    builds.value = {
      ...builds.value,
      [selectedCharacter.value]: normalizeConfig(saved || config),
    };
    infoText.value = `已保存 ${selectedCharacter.value} 的配装配置。`;
  } catch (error) {
    errorText.value = errorMessageOf(error);
  } finally {
    isSaving.value = false;
  }
}

async function runOptimize() {
  if (!canRun.value) return;
  isOptimizing.value = true;
  errorText.value = '';
  optimizeResult.value = null;
  try {
    optimizeResult.value = await callApi('get_optimize_combo', selectedCharacter.value, buildRunConfig());
  } catch (error) {
    errorText.value = errorMessageOf(error);
  } finally {
    isOptimizing.value = false;
  }
}

async function runPromising() {
  if (!selectedCharacter.value) return;
  isFindingPromising.value = true;
  errorText.value = '';
  promisingResults.value = [];
  try {
    promisingResults.value = normalizeRecommendations(
      await callApi('get_promising_disks', selectedCharacter.value, {
        ...advisorOptions.value,
        config: buildRunConfig(),
      }),
    );
  } catch (error) {
    errorText.value = errorMessageOf(error);
  } finally {
    isFindingPromising.value = false;
  }
}

async function locateDisk(disk) {
  try {
    const result = await callApi('locate_disk', disk);
    const target = result?.target || {};
    infoText.value = `${result?.message || '定位预览已生成'}：P${target.page ?? '-'} / R${target.row ?? '-'} / C${target.column ?? '-'}`;
  } catch (error) {
    errorText.value = errorMessageOf(error);
  }
}

function normalizeRecommendations(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.recommendations)) return payload.recommendations;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}

function buildMockOptimizeResult(characterName, config) {
  const selected = [1, 2, 3, 4, 5, 6].map((slot) => mockDisks.find((item) => item.slot === slot)).filter(Boolean);
  const weights = normalizeWeights(config?.weights || selectedBuild.value?.weights);
  const scoreBreakdown = selected.map((item) => ({
    disk: item,
    score: scoreDisk(item, weights),
  }));
  const setCounts = selected.reduce((acc, item) => {
    acc[item.set_name] = (acc[item.set_name] || 0) + 1;
    return acc;
  }, {});
  const target4 = config?.preferred_sets?.target_set_4 || config?.target_set_4;
  const target2 = config?.preferred_sets?.target_set_2 || config?.target_set_2;
  const exact = target4 && target2 && setCounts[target4] >= 4 && setCounts[target2] >= 2;
  return {
    character_name: characterName,
    combo: selected,
    total_score: round(scoreBreakdown.reduce((sum, item) => sum + item.score, 0)),
    set_counts: setCounts,
    match_type: exact ? 'exact_4_2' : 'target_4_any_2',
    is_fallback: !exact,
    warnings: exact ? [] : ['mock 数据未完全命中目标 4+2，已展示降级组合。'],
    score_breakdown: scoreBreakdown,
  };
}

function buildMockPromisingResults() {
  return mockDisks
    .filter((item) => Number(item.level || 0) < 15)
    .slice(0, 5)
    .map((item, index) => ({
      disk: item,
      rank: index < 2 ? 'high' : 'medium',
      potential_score: round(32 - index * 3.8),
      current_score: round(10 + index * 1.7),
      reasons: [
        '未满级驱动盘',
        '包含角色有效副词条',
        `仓库位置：${warehouseLabel(item)}`,
      ],
    }));
}

function scoreDisk(item, weights) {
  const main = statName(item.main_stat);
  const mainScore = (Number(item.main_stat?.value) || 0) * (weights[main] || 0) * 2;
  const subScore = (item.sub_stats || []).reduce((sum, sub) => sum + (Number(sub.value) || 0) * (weights[statName(sub)] || 0), 0);
  return round(mainScore + subScore);
}

function round(value) {
  return Math.round(Number(value || 0) * 10000) / 10000;
}

function addWeight() {
  draft.value.weights.push({ name: '', value: 1 });
}

function removeWeight(index) {
  draft.value.weights.splice(index, 1);
  if (!draft.value.weights.length) addWeight();
}

function statName(statValue) {
  if (statValue && typeof statValue === 'object') return statValue.name || statValue.stat_name || '-';
  return statValue || '-';
}

function isMainStatSelected(target, slot, stat) {
  return Array.isArray(target?.preferred_main_stats?.[slot]) && target.preferred_main_stats[slot].includes(stat);
}

function toggleMainStat(target, slot, stat) {
  if (!Array.isArray(target.preferred_main_stats[slot])) {
    target.preferred_main_stats[slot] = [];
  }
  const selected = target.preferred_main_stats[slot];
  const index = selected.indexOf(stat);
  if (index >= 0) {
    selected.splice(index, 1);
  } else {
    selected.push(stat);
  }
}

function statValue(statValue) {
  if (statValue && typeof statValue === 'object') return statValue.value ?? '-';
  return '-';
}

function subStatsOf(disk) {
  return Array.isArray(disk?.sub_stats) ? disk.sub_stats : [];
}

function diskId(item, index) {
  return item?.id || item?.disk_id || `${item?.slot || 'disk'}-${index}`;
}

function warehouseLabel(item) {
  const raw = item?.warehouse_location || item?.location || item?.position || item?.source || item?.inventory_pos;
  if (!raw) return '未知';
  if (typeof raw === 'string') return raw;
  const page = raw.page ?? raw.p ?? raw[0] ?? '-';
  const row = raw.row ?? raw.r ?? raw[1] ?? '-';
  const col = raw.col ?? raw.c ?? raw[2] ?? '-';
  return `P${page} / R${row} / C${col}`;
}

function diskStyle(item) {
  const asset = item?.asset || item?.image || item?.icon || SET_ICON_ASSETS[item?.set_name] || DISK_PLACEHOLDER_ASSET;
  if (asset) {
    return {
      backgroundImage: `url("${asset}")`,
      backgroundPosition: 'center',
      backgroundSize: 'cover',
    };
  }
  return {
    background:
      'radial-gradient(circle at 50% 50%, #f6ce00 0 6%, #09090b 7% 13%, #d4d4d8 14% 15%, #18181b 16% 32%, #71717a 33% 34%, #09090b 35% 52%, #3f3f46 53% 55%, #18181b 56% 100%)',
  };
}

function statIconStyle(name) {
  const asset = STAT_ICON_ASSETS[name] || '';
  return asset
    ? { backgroundImage: `url("${asset}")`, backgroundPosition: 'center', backgroundSize: 'cover' }
    : {};
}

function rankLabel(rank) {
  const labels = { high: '高潜力', medium: '中潜力', low: '低潜力' };
  return labels[rank] || rank || '-';
}

onMounted(loadInitialData);
</script>

<template>
  <section class="mx-auto grid max-w-7xl gap-5 px-4 py-6 xl:grid-cols-[380px_minmax(0,1fr)]">
    <aside class="space-y-5">
      <div class="panel shadow-hard">
        <div class="panel-title flex items-center justify-between gap-3">
          <span>配装控制</span>
        </div>
        <div class="space-y-4 p-4">
          <label class="block">
            <span class="field-label">角色选择</span>
            <select v-model="selectedCharacter" class="hard-input mt-2 w-full" :disabled="isLoading || !characterNames.length">
              <option v-for="name in characterNames" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>

          <div class="grid grid-cols-2 gap-3">
            <div class="metric-box">
              <span>驱动盘</span>
              <strong>{{ currentDisks.length }}</strong>
            </div>
            <div class="metric-box">
              <span>角色配置</span>
              <strong>{{ characterNames.length }}</strong>
            </div>
          </div>

          <p v-if="infoText" class="notice-box border-[#f6ce00] text-[#f6ce00]">{{ infoText }}</p>
          <p v-if="errorText" class="notice-box border-red-500 text-red-200">{{ errorText }}</p>

          <div class="grid grid-cols-2 gap-3">
            <button class="hard-button" type="button" :disabled="isLoading" @click="loadInitialData">
              {{ isLoading ? '刷新中' : '刷新数据' }}
            </button>
            <button class="hard-button hard-button-active" type="button" :disabled="!selectedCharacter || isSaving" @click="saveBuild">
              {{ isSaving ? '保存中' : '保存配置' }}
            </button>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">盘池概况</div>
        <div class="space-y-3 p-4">
          <div class="grid grid-cols-6 gap-2">
            <div v-for="(count, slot) in diskSummary.slots" :key="slot" class="slot-box">
              <span>{{ slot }}</span>
              <strong>{{ count }}</strong>
            </div>
          </div>
          <div class="max-h-64 space-y-2 overflow-auto">
            <div v-for="(count, name) in diskSummary.sets" :key="name" class="flex min-w-0 items-center justify-between gap-3 rounded-sm border-2 border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-xs font-black">
              <span class="truncate">{{ name }}</span>
              <span class="text-[#f6ce00]">{{ count }}</span>
            </div>
            <p v-if="!currentDisks.length" class="font-mono text-xs font-bold text-zinc-500">暂无当前盘池数据。</p>
          </div>
        </div>
      </div>
    </aside>

    <div class="space-y-5">
      <div class="grid gap-5 lg:grid-cols-2">
        <div class="panel">
          <div class="panel-title flex items-center justify-between gap-3">
            <span>属性权重</span>
            <button class="hard-button py-1" type="button" @click="addWeight">新增</button>
          </div>
          <div class="space-y-3 p-4">
            <div v-for="(item, index) in draft.weights" :key="index" class="grid grid-cols-[minmax(0,1fr)_92px_auto] gap-2">
              <input v-model="item.name" class="hard-input min-w-0" type="text" placeholder="属性名" />
              <input v-model.number="item.value" class="hard-input" type="number" step="0.05" />
              <button class="hard-button px-3" type="button" :disabled="draft.weights.length <= 1" @click="removeWeight(index)">删</button>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">推荐目标</div>
          <div class="space-y-4 p-4">
            <div class="grid gap-3 sm:grid-cols-3">
              <label v-for="slot in [4, 5, 6]" :key="slot" class="block">
                <span class="field-label">{{ slot }} 号位主属性</span>
                <div class="mt-2 max-h-44 overflow-auto rounded-sm border-2 border-zinc-800 bg-zinc-950 p-2">
                  <button
                    v-for="stat in mainStatOptions"
                    :key="`${slot}-${stat}`"
                    class="stat-choice"
                    :class="{ 'stat-choice-active': isMainStatSelected(draft, slot, stat) }"
                    type="button"
                    @click="toggleMainStat(draft, slot, stat)"
                  >
                    {{ stat }}
                  </button>
                </div>
              </label>
            </div>
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="block">
                <span class="field-label">四件套目标</span>
                <input v-model="draft.preferred_sets.target_set_4" class="hard-input mt-2 w-full" list="set-options" type="text" />
              </label>
              <label class="block">
                <span class="field-label">二件套目标</span>
                <input v-model="draft.preferred_sets.target_set_2" class="hard-input mt-2 w-full" list="set-options" type="text" />
              </label>
            </div>
            <datalist id="set-options">
              <option v-for="setName in currentSetNames" :key="setName" :value="setName" />
            </datalist>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">运行配置</div>
        <div class="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div class="grid gap-4 md:grid-cols-2">
            <label class="block md:col-span-1">
              <span class="field-label">临时四件套</span>
              <input v-model="overrideConfig.target_set_4" class="hard-input mt-2 w-full" list="set-options" type="text" placeholder="留空沿用" />
            </label>
            <label class="block md:col-span-1">
              <span class="field-label">临时二件套</span>
              <input v-model="overrideConfig.target_set_2" class="hard-input mt-2 w-full" list="set-options" type="text" placeholder="留空沿用" />
            </label>
            <div class="md:col-span-2 grid gap-3 lg:grid-cols-3">
              <label v-for="slot in [4, 5, 6]" :key="slot" class="block">
                <span class="field-label">临时 {{ slot }} 号位主属性</span>
                <div class="mt-2 max-h-36 overflow-auto rounded-sm border-2 border-zinc-800 bg-zinc-950 p-2">
                  <button
                    v-for="stat in mainStatOptions"
                    :key="`override-${slot}-${stat}`"
                    class="stat-choice"
                    :class="{ 'stat-choice-active': isMainStatSelected(overrideConfig, slot, stat) }"
                    type="button"
                    @click="toggleMainStat(overrideConfig, slot, stat)"
                  >
                    {{ stat }}
                  </button>
                </div>
              </label>
            </div>
          </div>
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
            <button class="hard-button hard-button-active w-full" type="button" :disabled="!canRun || isOptimizing" @click="runOptimize">
              {{ isOptimizing ? '计算中' : '运行最优组合' }}
            </button>
            <button class="hard-button w-full" type="button" :disabled="!selectedCharacter || isFindingPromising" @click="runPromising">
              {{ isFindingPromising ? '筛选中' : '运行胚子推荐' }}
            </button>
          </div>
        </div>
      </div>

      <div class="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <div class="panel">
          <div class="panel-title flex items-center justify-between gap-3">
            <span>最优组合结果</span>
            <span v-if="optimizeResult" class="text-zinc-300">总分 {{ optimizeResult.total_score ?? '-' }}</span>
          </div>
          <div v-if="optimizeResult" class="space-y-4 p-4">
            <div class="grid gap-3 md:grid-cols-4">
              <div class="metric-box">
                <span>匹配类型</span>
                <strong class="text-base">{{ optimizeResult.match_type || '-' }}</strong>
              </div>
              <div class="metric-box">
                <span>降级</span>
                <strong class="text-base">{{ optimizeResult.is_fallback ? '是' : '否' }}</strong>
              </div>
              <div class="metric-box">
                <span>总分</span>
                <strong>{{ optimizeResult.total_score ?? '-' }}</strong>
              </div>
              <div class="metric-box">
                <span>警告</span>
                <strong>{{ optimizeResult.warnings?.length || 0 }}</strong>
              </div>
            </div>

            <div v-if="optimizeResult.warnings?.length" class="space-y-2">
              <p v-for="warning in optimizeResult.warnings" :key="warning" class="notice-box border-amber-400 text-amber-200">{{ warning }}</p>
            </div>

            <div class="grid gap-3 md:grid-cols-2">
              <div class="rounded-sm border-2 border-zinc-800 bg-zinc-950 p-3">
                <p class="field-label">套装计数</p>
                <div class="mt-3 space-y-2">
                  <div v-for="(count, setName) in optimizeResult.set_counts" :key="setName" class="flex justify-between gap-3 font-mono text-xs font-black">
                    <span class="truncate text-zinc-300">{{ setName }}</span>
                    <span class="text-[#f6ce00]">{{ count }}</span>
                  </div>
                </div>
              </div>
              <div class="rounded-sm border-2 border-zinc-800 bg-zinc-950 p-3">
                <p class="field-label">得分拆解</p>
                <div class="mt-3 space-y-2">
                  <div v-for="(item, index) in optimizeResult.score_breakdown || []" :key="diskId(item.disk, index)" class="flex justify-between gap-3 font-mono text-xs font-black">
                    <span class="truncate text-zinc-300">{{ item.disk?.slot }}号位 {{ item.disk?.set_name }}</span>
                    <span class="text-[#f6ce00]">{{ item.score }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
              <article v-for="(item, index) in optimizeResult.combo || []" :key="diskId(item, index)" class="disk-card">
                <div class="flex gap-3">
                  <div class="disk-vinyl" :style="diskStyle(item)"></div>
                  <div class="min-w-0 flex-1">
                    <p class="truncate font-mono text-xs font-black text-[#f6ce00]">{{ item.slot }} 号位</p>
                    <h3 class="truncate text-sm font-black">{{ item.set_name || '未知套装' }}</h3>
                    <p class="mt-1 truncate font-mono text-xs text-zinc-400">主词条：{{ statName(item.main_stat) }} {{ statValue(item.main_stat) }}</p>
                    <p class="mt-2 font-mono text-[11px] font-bold text-zinc-500">{{ warehouseLabel(item) }}</p>
                  </div>
                </div>
                <div class="mt-3 border-t-2 border-zinc-800 pt-3">
                  <p class="mb-2 font-mono text-xs font-black text-zinc-500">副词条</p>
                  <div v-if="subStatsOf(item).length" class="grid grid-cols-2 gap-2">
                    <span
                      v-for="sub in subStatsOf(item)"
                      :key="`${item.id || index}-${statName(sub)}-${statValue(sub)}`"
                      class="rounded-sm border-2 border-zinc-800 bg-zinc-900 px-2 py-1 font-mono text-[11px] font-black text-zinc-300"
                    >
                      {{ statName(sub) }} {{ statValue(sub) }}
                    </span>
                  </div>
                  <p v-else class="font-mono text-xs font-bold text-zinc-600">暂无副词条</p>
                </div>
                <button class="mt-3 hard-button w-full py-2" type="button" @click="locateDisk(item)">
                  定位到游戏中（预留）
                </button>
              </article>
            </div>
          </div>
          <div v-else class="empty-state">尚未运行最优组合。</div>
        </div>

        <div class="panel">
          <div class="panel-title">培养推荐</div>
          <div class="space-y-4 p-4">
            <div class="grid grid-cols-2 gap-3">
              <label class="block">
                <span class="field-label">有效副词条下限</span>
                <input v-model.number="advisorOptions.min_effective_sub_stats" class="hard-input mt-2 w-full" min="0" step="1" type="number" />
              </label>
              <label class="block">
                <span class="field-label">高权重阈值</span>
                <input v-model.number="advisorOptions.high_weight_threshold" class="hard-input mt-2 w-full" min="0" step="0.1" type="number" />
              </label>
            </div>

            <div class="max-h-[720px] space-y-3 overflow-auto pr-1">
              <article v-for="(item, index) in promisingResults" :key="diskId(item.disk, index)" class="disk-card">
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <p class="font-mono text-xs font-black text-[#f6ce00]">{{ rankLabel(item.rank) }}</p>
                    <h3 class="truncate text-sm font-black">{{ item.disk?.slot }}号位 {{ item.disk?.set_name || '未知套装' }}</h3>
                  </div>
                  <div class="shrink-0 text-right font-mono text-xs font-black">
                    <p class="text-[#f6ce00]">{{ item.potential_score }}</p>
                    <p class="text-zinc-500">当前 {{ item.current_score }}</p>
                  </div>
                </div>
                <div class="mt-3 flex gap-3">
                  <div class="disk-vinyl h-14 w-14" :style="diskStyle(item.disk)"></div>
                  <div class="min-w-0 flex-1 font-mono text-xs font-bold text-zinc-300">
                    <p class="truncate">主词条：{{ statName(item.disk?.main_stat) }} {{ statValue(item.disk?.main_stat) }}</p>
                    <p class="truncate">仓库：{{ warehouseLabel(item.disk) }}</p>
                  </div>
                </div>
                <div class="mt-3 grid grid-cols-2 gap-2">
                  <span
                    v-for="sub in subStatsOf(item.disk)"
                    :key="`${item.disk?.id || index}-${statName(sub)}-${statValue(sub)}`"
                    class="rounded-sm border-2 border-zinc-800 bg-zinc-900 px-2 py-1 font-mono text-[11px] font-black text-zinc-300"
                  >
                    {{ statName(sub) }} {{ statValue(sub) }}
                  </span>
                </div>
                <div class="mt-3 flex flex-wrap gap-2">
                  <span v-for="reason in item.reasons || []" :key="reason" class="reason-chip">{{ reason }}</span>
                </div>
                <button class="mt-3 hard-button w-full py-2" type="button" @click="locateDisk(item.disk)">
                  定位到游戏中（预留）
                </button>
              </article>
              <div v-if="!promisingResults.length" class="empty-state">尚未运行胚子推荐。</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
