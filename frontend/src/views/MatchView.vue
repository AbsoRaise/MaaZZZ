<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { diskIconFor } from '../diskIcons';

const DISK_PLACEHOLDER_ASSET = '';
const STAT_ICON_ASSETS = {};
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
const advisorOptions = ref({
  min_effective_sub_stats: 1,
  high_weight_threshold: 0.8,
});
const optimizeResult = ref(null);
const promisingResults = ref([]);
const promisingSlot = ref(1);
const hasRunOptimize = ref(false);
const hasRunPromising = ref(false);
const collapsed = ref({
  weights: false,
  target: false,
  actions: false,
  result: false,
  promising: false,
});

const characterNames = computed(() => Object.keys(builds.value));
const selectedBuild = computed(() => builds.value[selectedCharacter.value] || null);
const canRun = computed(() => Boolean(selectedCharacter.value) && currentDisks.value.length > 0);
const promisingSlotGroups = computed(() => {
  return [1, 2, 3, 4, 5, 6]
    .map((slot) => {
      const items = promisingResults.value
        .filter((item) => Number(item?.disk?.slot || 0) === slot)
        .sort((a, b) => {
          const scoreDelta = Number(b?.potential_score || 0) - Number(a?.potential_score || 0);
          if (scoreDelta) return scoreDelta;
          return Number(b?.current_score || 0) - Number(a?.current_score || 0);
        });
      return { slot, items };
    })
    .filter((group) => group.items.length);
});
const activePromisingGroup = computed(() => {
  return (
    promisingSlotGroups.value.find((group) => group.slot === promisingSlot.value) ||
    promisingSlotGroups.value[0] ||
    { slot: promisingSlot.value, items: [] }
  );
});
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
  promisingSlot.value = 1;
  hasRunOptimize.value = false;
  hasRunPromising.value = false;
});

watch(promisingResults, () => {
  const availableSlots = promisingSlotGroups.value.map((group) => group.slot);
  if (!availableSlots.length) {
    promisingSlot.value = 1;
    return;
  }
  if (!availableSlots.includes(promisingSlot.value)) {
    promisingSlot.value = availableSlots[0];
  }
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
    optimizeResult.value = null;
    promisingResults.value = [];
    hasRunOptimize.value = false;
    hasRunPromising.value = false;
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
  return draftToConfig();
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
    emitAppLog('信息', infoText.value);
  } catch (error) {
    errorText.value = errorMessageOf(error);
    emitAppLog('错误', '保存配装配置失败。', errorMessageOf(error));
  } finally {
    isSaving.value = false;
  }
}

async function runOptimize() {
  if (!canRun.value) return;
  isOptimizing.value = true;
  errorText.value = '';
  optimizeResult.value = null;
  hasRunOptimize.value = false;
  try {
    optimizeResult.value = await callApi('get_optimize_combo', selectedCharacter.value, buildRunConfig());
    hasRunOptimize.value = true;
    collapsed.value.result = false;
    emitAppLog('事件', `最优组合计算完成：总分 ${optimizeResult.value?.total_score ?? '-'}`, {
      匹配类型: matchTypeLabel(optimizeResult.value?.match_type),
      计算日志: optimizeResult.value?.optimize_logs || [],
    });
  } catch (error) {
    errorText.value = errorMessageOf(error);
    emitAppLog('错误', '最优组合计算失败。', errorMessageOf(error));
  } finally {
    isOptimizing.value = false;
  }
}

async function runPromising() {
  if (!selectedCharacter.value) return;
  isFindingPromising.value = true;
  errorText.value = '';
  promisingResults.value = [];
  hasRunPromising.value = false;
  try {
    promisingResults.value = normalizeRecommendations(
      await callApi('get_promising_disks', selectedCharacter.value, {
        ...advisorOptions.value,
        config: buildRunConfig(),
      }),
    );
    hasRunPromising.value = true;
    collapsed.value.promising = false;
    const firstSlot = [1, 2, 3, 4, 5, 6].find((slot) =>
      promisingResults.value.some((item) => Number(item?.disk?.slot || 0) === slot),
    );
    promisingSlot.value = firstSlot || 1;
    emitAppLog('事件', `培养推荐计算完成：${promisingResults.value.length} 条结果。`);
  } catch (error) {
    errorText.value = errorMessageOf(error);
    emitAppLog('错误', '培养推荐计算失败。', errorMessageOf(error));
  } finally {
    isFindingPromising.value = false;
  }
}

async function locateDisk(disk) {
  try {
    const result = await callApi('locate_disk', disk);
    const target = result?.target || {};
    infoText.value = `${result?.message || '定位预览已生成'}：${warehouseLabel({ inventory_pos: target })}`;
    emitAppLog('事件', infoText.value, disk);
  } catch (error) {
    errorText.value = errorMessageOf(error);
    emitAppLog('错误', '定位驱动盘失败。', errorMessageOf(error));
  }
}

function emitAppLog(level, message, detail = '') {
  window.dispatchEvent(
    new CustomEvent('app-log', {
      detail: { level, message, detail },
    }),
  );
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
  const preferredMainStats = normalizePreferredMainStats(config?.preferred_main_stats || selectedBuild.value?.preferred_main_stats);
  const scoreBreakdown = selected.map((item) => ({
    disk: item,
    score: scoreDisk(item, weights, preferredMainStats),
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
    optimize_logs: [
      `候选数量: ${JSON.stringify(selected.reduce((acc, item) => ({ ...acc, [item.slot]: (acc[item.slot] || 0) + 1 }), {}))}`,
      '演示模式未连接后端，实际运行时会显示原始组合数、压缩后候选数、状态数和耗时。',
    ],
  };
}

function buildMockPromisingResults() {
  const weights = normalizeWeights(selectedBuild.value?.weights);
  const preferredMainStats = normalizePreferredMainStats(selectedBuild.value?.preferred_main_stats);
  const recommendedSets = recommendedSetNames(draftToConfig().preferred_sets || selectedBuild.value?.preferred_sets);
  return mockDisks
    .filter((item) => !recommendedSets.length || recommendedSets.includes(item.set_name || item.set))
    .slice(0, 5)
    .map((item) => {
      const currentScore = scoreDisk(item, weights, preferredMainStats);
      const effectiveCount = (item.sub_stats || []).filter((sub) => (weights[statName(sub)] || 0) > 0).length;
      const highCount = (item.sub_stats || []).filter((sub) => (weights[statName(sub)] || 0) >= Number(advisorOptions.value.high_weight_threshold || 0)).length;
      const effectiveRollCount = (item.sub_stats || []).reduce((sum, sub) => sum + ((weights[statName(sub)] || 0) > 0 ? subStatCount(sub) : 0), 0);
      const highRollCount = (item.sub_stats || []).reduce((sum, sub) => sum + ((weights[statName(sub)] || 0) >= Number(advisorOptions.value.high_weight_threshold || 0) ? subStatCount(sub) : 0), 0);
      const weightedRollScore = weightedSubStatRollScore(item, weights);
      const maxStatWeight = maxWeightOf(weights);
      const remainingUpgradeCount = remainingUpgradeCountFor(item);
      const maxVisibleRollCount = maxVisibleSubStatRollCountFor(item);
      const potentialScore = potentialScoreFor(item, weightedRollScore, maxStatWeight, preferredMainStats);
      return {
        disk: item,
        rank: potentialScore >= 25 ? 'high' : potentialScore >= 12 ? 'medium' : 'low',
        potential_score: potentialScore,
        current_score: currentScore,
        effective_sub_stat_roll_count: effectiveRollCount,
        high_value_sub_stat_roll_count: highRollCount,
        weighted_sub_stat_roll_score: round(weightedRollScore),
        max_stat_weight: maxStatWeight,
        remaining_upgrade_count: remainingUpgradeCount,
        max_visible_sub_stat_roll_count: maxVisibleRollCount,
        reasons: [
          remainingUpgradeCount > 0 ? '未满级驱动盘' : '已满级驱动盘',
          `包含 ${effectiveCount} 条角色有效副词条`,
          `包含 ${highCount} 条高价值副词条`,
          `剩余 ${remainingUpgradeCount} 次副词条升级机会`,
          `当前等级最多已出现 ${maxVisibleRollCount} 次副词条`,
          `仓库位置：${warehouseLabel(item)}`,
        ],
      };
    });
}

function recommendedSetNames(preferredSets) {
  if (!preferredSets || typeof preferredSets !== 'object') return [];
  const names = [preferredSets.target_set_4, preferredSets.target_set_2].filter(Boolean);
  const alternatives = Array.isArray(preferredSets.alternatives) ? preferredSets.alternatives : [];
  alternatives.forEach((item) => {
    if (typeof item === 'string' && item) {
      names.push(item);
      return;
    }
    if (item && typeof item === 'object') {
      ['target_set_4', 'target_set_2', 'set_name', 'set'].forEach((key) => {
        if (item[key]) names.push(item[key]);
      });
    }
  });
  return [...new Set(names.map((item) => String(item).trim()).filter(Boolean))];
}

function scoreDisk(item, weights, preferredMainStats = {}) {
  const slot = Number(item?.slot || 0);
  const maxWeight = slotMaxWeight(slot, weights, preferredMainStats);
  if (!maxWeight) return 0;
  const subWeight = (item.sub_stats || []).reduce((sum, sub) => sum + subStatCount(sub) * (weights[statName(sub)] || 0), 0);
  const mainName = statName(item?.main_stat);
  const wantedMainStats = preferredMainStats?.[slot] || [];
  const mainUseful = !wantedMainStats.length || wantedMainStats.includes(mainName);
  const mainWeight = slot >= 4 && slot <= 6 && mainUseful
    ? 3 * (weights[mainName] || 0) * mainLevelMultiplier(item)
    : 0;
  return round(Math.min(55, (subWeight + mainWeight) * (55 / maxWeight)) * rarityMultiplier(item));
}

function currentWeights() {
  return normalizeWeights(draftToConfig().weights);
}

function currentPreferredMainStats() {
  return normalizePreferredMainStats(draft.value.preferred_main_stats);
}

function isEffectiveSubStat(sub) {
  return Number(currentWeights()[statName(sub)] || 0) > 0;
}

function subStatTitle(sub) {
  const weight = Number(currentWeights()[statName(sub)] || 0);
  const count = subStatCount(sub);
  if (weight <= 0) return '该副词条未配置有效权重，不计入当前得分。';
  return `有效副词条：${statName(sub)}\n词条次数：1 + ${statUpgradeCount(sub)} = ${count}\n权重：${weight}\n贡献权重：${count} × ${weight} = ${formatNumber(count * weight)}`;
}

function scoreFormulaTitle(item, displayedScore = null) {
  const weights = currentWeights();
  const preferredMainStats = currentPreferredMainStats();
  const slot = Number(item?.slot || 0);
  const maxWeight = slotMaxWeight(slot, weights, preferredMainStats);
  if (!maxWeight) return '当前没有可用于计算的有效属性权重。';

  const subLines = subStatsOf(item).map((sub) => {
    const name = statName(sub);
    const count = subStatCount(sub);
    const weight = Number(weights[name] || 0);
    return `${name}: ${count} × ${formatNumber(weight)} = ${formatNumber(count * weight)}`;
  });
  const subWeight = subStatsOf(item).reduce((sum, sub) => sum + subStatCount(sub) * Number(weights[statName(sub)] || 0), 0);
  const mainName = statName(item?.main_stat);
  const wantedMainStats = preferredMainStats?.[slot] || [];
  const mainUseful = slot >= 4 && slot <= 6 && (!wantedMainStats.length || wantedMainStats.includes(mainName));
  const mainBaseWeight = Number(weights[mainName] || 0);
  const mainMultiplier = mainLevelMultiplier(item);
  const mainWeight = mainUseful ? 3 * mainBaseWeight * mainMultiplier : 0;
  const rawScore = (subWeight + mainWeight) * (55 / maxWeight);
  const cappedScore = Math.min(55, rawScore);
  const rarityRate = rarityMultiplier(item);
  const finalScore = displayedScore ?? round(cappedScore * rarityRate);

  return [
    `得分计算：${displayScore(finalScore)}`,
    `副词条贡献：${formatNumber(subWeight)}`,
    ...(subLines.length ? subLines : ['无副词条']),
    `主词条贡献：${formatNumber(mainWeight)}`,
    slot >= 4 && slot <= 6
      ? `${mainName}: 3 × ${formatNumber(mainBaseWeight)} × ${formatNumber(mainMultiplier)} = ${formatNumber(mainWeight)}${mainUseful ? '' : '（主属性未命中推荐目标，不计分）'}`
      : '1-3 号位主词条固定，不参与主词条加权。',
    `部位满分权重：${formatNumber(maxWeight)}`,
    '副词条满分按“初始最多 4 条有效副词条 + 5 次升级全部给最高权重词条”估算。',
    `归一化：(${formatNumber(subWeight)} + ${formatNumber(mainWeight)}) × 55 / ${formatNumber(maxWeight)} = ${formatNumber(rawScore)}`,
    `品质倍率：${rarityOf(item)} × ${formatNumber(rarityRate)}`,
    `最终：min(55, ${formatNumber(rawScore)}) × ${formatNumber(rarityRate)} = ${displayScore(finalScore)}`,
  ].join('\n');
}

function potentialFormulaTitle(item) {
  const weights = currentWeights();
  const weightedRollScore = Number(item?.weighted_sub_stat_roll_score ?? weightedSubStatRollScore(item?.disk, weights));
  const maxStatWeight = Number(item?.max_stat_weight ?? maxWeightOf(weights));
  const remainingUpgradeCount = Number(item?.remaining_upgrade_count ?? remainingUpgradeCountFor(item?.disk));
  const maxVisibleRollCount = Number(item?.max_visible_sub_stat_roll_count ?? maxVisibleSubStatRollCountFor(item?.disk));
  const visibleQuality = maxStatWeight > 0 ? (weightedRollScore * 6) / maxStatWeight : 0;
  const qualityPerVisibleRoll = maxVisibleRollCount > 0 ? visibleQuality / maxVisibleRollCount : 0;
  const mainFactor = mainStatFactorFor(item?.disk);
  const statLines = subStatsOf(item?.disk)
    .map((sub) => {
      const name = statName(sub);
      const count = subStatCount(sub);
      const weight = Number(weights[name] || 0);
      if (weight <= 0) return null;
      return `${name}: ${count} × ${formatNumber(weight)} = ${formatNumber(count * weight)}`;
    })
    .filter(Boolean);
  return [
    `潜力分：${displayScore(item?.potential_score)}`,
    `当前分：${displayScore(item?.current_score)}`,
    `当前等级最多已出现：${maxVisibleRollCount} 次副词条`,
    `剩余升级次数：${remainingUpgradeCount} 次`,
    `加权词条贡献：${formatNumber(weightedRollScore)}`,
    ...(statLines.length ? statLines : ['没有命中有效副词条']),
    `权重归一：${formatNumber(weightedRollScore)} × 6 / ${formatNumber(maxStatWeight)} = ${formatNumber(visibleQuality)}`,
    `可见平均质量：${formatNumber(visibleQuality)} / ${maxVisibleRollCount} = ${formatNumber(qualityPerVisibleRoll)}`,
    `主属性系数：${formatNumber(mainFactor)}`,
    remainingUpgradeCount <= 0
      ? '最终：15级驱动盘没有剩余升级机会，潜力分 = 0'
      : `最终：min(55, ${formatNumber(qualityPerVisibleRoll)} × ${remainingUpgradeCount}) × ${formatNumber(mainFactor)} = ${displayScore(item?.potential_score)}`,
  ].join('\n');
}

function slotMaxWeight(slot, weights, preferredMainStats) {
  const positive = Object.entries(weights || {}).filter(([, weight]) => Number(weight) > 0);
  if (!positive.length) return 0;
  if (slot < 4 || slot > 6) return maxSubWeight(positive.map(([, weight]) => Number(weight)));
  const preferred = (preferredMainStats?.[slot] || []).filter((stat) => Number(weights[stat] || 0) > 0);
  if (!preferred.length) return maxSubWeight(positive.map(([, weight]) => Number(weight)));
  return Math.max(
    ...preferred.map((mainStat) => {
      const subWeights = positive.filter(([stat]) => stat !== mainStat).map(([, weight]) => Number(weight));
      return maxSubWeight(subWeights) + 3 * Number(weights[mainStat] || 0);
    }),
  );
}

function maxSubWeight(weights) {
  const sorted = weights.filter((weight) => weight > 0).sort((a, b) => b - a).slice(0, 4);
  if (!sorted.length) return 0;
  return sorted.reduce((sum, weight) => sum + weight, 0) + 5 * sorted[0];
}

function subStatCount(sub) {
  return Math.max(1, 1 + (Number(sub?.upgrade ?? sub?.upgrade_count ?? 0) || 0));
}

function mainLevelMultiplier(item) {
  const level = Math.max(0, Number(item?.level || 0));
  return Math.max(0.25, Math.min(1, 0.25 + level * 0.05));
}

function remainingUpgradeCountFor(item) {
  const level = Math.max(0, Number(item?.level || 0));
  if (level >= 15) return 0;
  if (level >= 12) return 1;
  if (level >= 9) return 2;
  if (level >= 6) return 3;
  if (level >= 3) return 4;
  return 5;
}

function maxVisibleSubStatRollCountFor(item) {
  return 9 - remainingUpgradeCountFor(item);
}

function maxWeightOf(weights) {
  const values = Object.values(weights || {}).map((value) => Number(value) || 0).filter((value) => value > 0);
  return values.length ? Math.max(...values) : 0;
}

function weightedSubStatRollScore(item, weights = currentWeights()) {
  return subStatsOf(item).reduce((sum, sub) => {
    const weight = Number(weights[statName(sub)] || 0);
    return weight > 0 ? sum + subStatCount(sub) * weight : sum;
  }, 0);
}

function mainStatFactorFor(item, preferredMainStats = currentPreferredMainStats()) {
  const slot = Number(item?.slot || 0);
  if (slot < 4 || slot > 6) return 1;
  const wantedMainStats = preferredMainStats?.[slot] || [];
  if (!wantedMainStats.length) return 1;
  return wantedMainStats.includes(statName(item?.main_stat)) ? 1 : 0.5;
}

function potentialScoreFor(item, weightedRollScore, maxStatWeight, preferredMainStats = currentPreferredMainStats()) {
  const remainingUpgradeCount = remainingUpgradeCountFor(item);
  if (remainingUpgradeCount <= 0 || maxStatWeight <= 0) return 0;
  const maxVisibleRollCount = maxVisibleSubStatRollCountFor(item);
  const visibleQuality = (weightedRollScore * 6) / maxStatWeight;
  const qualityPerVisibleRoll = maxVisibleRollCount > 0 ? visibleQuality / maxVisibleRollCount : 0;
  return round(Math.min(55, qualityPerVisibleRoll * remainingUpgradeCount) * mainStatFactorFor(item, preferredMainStats));
}

function rarityMultiplier(item) {
  const rarity = String(item?.rarity || 'S').toUpperCase();
  if (rarity === 'A') return 0.67;
  if (rarity === 'B') return 0.33;
  return 1;
}

function round(value) {
  return Math.round(Number(value || 0) * 10000) / 10000;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '0';
  return Number.isInteger(number) ? String(number) : number.toFixed(4).replace(/0+$/g, '').replace(/\.$/g, '');
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

function statUpgradeCount(statValue) {
  if (!statValue || typeof statValue !== 'object') return 0;
  return Number(statValue.upgrade ?? statValue.upgrade_count ?? 0) || 0;
}

function subStatsOf(disk) {
  return Array.isArray(disk?.sub_stats) ? disk.sub_stats : [];
}

function diskId(item, index) {
  return item?.id || item?.disk_id || `${item?.slot || 'disk'}-${index}`;
}

function rarityOf(disk) {
  return String(disk?.rarity || disk?.rank || 'S').toUpperCase();
}

function rarityClass(disk) {
  const rarity = rarityOf(disk);
  if (rarity === 'A') return 'disk-rarity-a';
  if (rarity === 'B') return 'disk-rarity-b';
  return 'disk-rarity-s';
}

function levelClass(disk) {
  const rarity = rarityOf(disk);
  if (rarity === 'A') return 'text-purple-300';
  if (rarity === 'B') return 'text-sky-300';
  return 'text-[#f6ce00]';
}

function comboItems(result) {
  const combo = Array.isArray(result?.combo) ? result.combo : [];
  return [0, 1, 2, 3, 4, 5].map((index) => combo[index] || null);
}

function comboScore(result, index) {
  const breakdown = Array.isArray(result?.score_breakdown) ? result.score_breakdown : [];
  return breakdown[index]?.score ?? 0;
}

function displayScore(value) {
  const score = Number(value);
  if (!Number.isFinite(score)) return '-';
  return Number.isInteger(score) ? String(score) : score.toFixed(1);
}

function comboSlotLabel(item, index) {
  return `${item?.slot || index + 1} 号位`;
}

function isEmptyComboSlot(item) {
  return !item || typeof item !== 'object';
}

function toggleSection(name) {
  collapsed.value[name] = !collapsed.value[name];
}

function collapseLabel(name) {
  return collapsed.value[name] ? '展开' : '收起';
}

function matchTypeLabel(type) {
  const labels = {
    exact_4_2: '命中目标 4+2',
    target_4_any_2: '命中四件套，二件套降级',
    any_4_2: '任意 4+2 套装',
    two_two_two: '三组二件套',
    best_score_only: '仅按分数最优',
  };
  return labels[type] || '未知匹配';
}

function selectedMainStatsSummary() {
  return [4, 5, 6]
    .map((slot) => {
      const stats = draft.value.preferred_main_stats?.[slot] || [];
      return `${slot}号位：${stats.length ? stats.join(' / ') : '未指定'}`;
    })
    .join('；');
}

function weightSummary() {
  const items = draft.value.weights
    .map((item) => ({ name: String(item.name || '').trim(), value: Number(item.value) || 0 }))
    .filter((item) => item.name);
  if (!items.length) return '未指定';
  return items.map((item) => `${item.name} × ${item.value}`).join('；');
}

function warehouseLabel(item) {
  const raw = item?.warehouse_location || item?.location || item?.position || item?.source || item?.inventory_pos;
  if (!raw) return '第 - 行 / 第 - 列';
  if (typeof raw === 'string') {
    const match = raw.match(/R\s*(\d+).*C\s*(\d+)/i) || raw.match(/第\s*(\d+)\s*行.*第\s*(\d+)\s*[列个]/);
    return match ? `第 ${match[1]} 行 / 第 ${match[2]} 列` : raw;
  }
  const row = raw.row ?? raw.r ?? raw[1] ?? '-';
  const col = raw.column ?? raw.col ?? raw.c ?? raw[2] ?? '-';
  return `第 ${row} 行 / 第 ${col} 列`;
}

function formatReason(reason) {
  const text = String(reason || '');
  const locationMatch = text.match(/^仓库位置[:：]\s*(.+)$/);
  if (!locationMatch) return text;
  return `仓库位置：${warehouseLabel({ warehouse_location: locationMatch[1] })}`;
}

function scoreLabel(item) {
  return `潜力 ${item?.potential_score ?? '-'} / 当前 ${item?.current_score ?? '-'}`;
}

function scoreTitle() {
  return '潜力分表示这块驱动盘未来剩余升级机会的培养价值；当前分表示这块驱动盘现在按属性权重计算出的得分。';
}

function diskStyle(item) {
  const asset = item?.asset || item?.image || item?.icon || diskIconFor(item?.set_name) || DISK_PLACEHOLDER_ASSET;
  const fallbackBackground =
    'radial-gradient(circle at 50% 50%, #f6ce00 0 6%, #09090b 7% 13%, #d4d4d8 14% 15%, #18181b 16% 32%, #71717a 33% 34%, #09090b 35% 52%, #3f3f46 53% 55%, #18181b 56% 100%)';
  if (asset) {
    return {
      backgroundImage: `url("${asset}"), ${fallbackBackground}`,
      backgroundPosition: 'center',
      backgroundSize: 'cover',
    };
  }
  return {
    background: fallbackBackground,
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

onMounted(async () => {
  await waitForApi();
  await loadInitialData();
});
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

    </aside>

    <div class="space-y-5">
      <div class="grid gap-5 lg:grid-cols-2">
        <div class="panel">
          <div class="panel-title flex items-center justify-between gap-3">
            <span>属性权重</span>
            <div class="flex shrink-0 gap-2">
              <button class="hard-button py-1" type="button" @click="addWeight">新增</button>
              <button class="hard-button py-1" type="button" @click="toggleSection('weights')">{{ collapseLabel('weights') }}</button>
            </div>
          </div>
          <div v-if="!collapsed.weights" class="space-y-3 p-4">
            <div v-for="(item, index) in draft.weights" :key="index" class="grid grid-cols-[minmax(0,1fr)_92px_auto] gap-2">
              <input v-model="item.name" class="hard-input min-w-0" type="text" placeholder="属性名" />
              <input v-model.number="item.value" class="hard-input" type="number" step="0.05" />
              <button class="hard-button px-3" type="button" :disabled="draft.weights.length <= 1" @click="removeWeight(index)">删</button>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title flex items-center justify-between gap-3">
            <span>推荐目标</span>
            <button class="hard-button py-1" type="button" @click="toggleSection('target')">{{ collapseLabel('target') }}</button>
          </div>
          <div v-if="!collapsed.target" class="space-y-4 p-4">
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
        <div class="panel-title flex items-center justify-between gap-3">
          <span>执行操作</span>
          <button class="hard-button py-1" type="button" @click="toggleSection('actions')">{{ collapseLabel('actions') }}</button>
        </div>
        <div v-if="!collapsed.actions" class="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div class="rounded-sm border-2 border-zinc-800 bg-zinc-950 p-3 font-mono text-xs font-bold text-zinc-300">
            <p class="text-[#f6ce00]">当前使用上方推荐目标进行计算。</p>
            <p class="mt-2">四件套：{{ draft.preferred_sets.target_set_4 || '未指定' }}</p>
            <p class="mt-1">二件套：{{ draft.preferred_sets.target_set_2 || '未指定' }}</p>
            <p class="mt-1">主属性：{{ selectedMainStatsSummary() }}</p>
            <p class="mt-1">副属性权重：{{ weightSummary() }}</p>
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

      <div v-if="hasRunOptimize || hasRunPromising" class="space-y-5">
        <div v-if="hasRunOptimize" class="panel">
          <div class="panel-title flex items-center justify-between gap-3">
            <span>最优组合结果</span>
            <div class="flex shrink-0 items-center gap-3">
              <span v-if="optimizeResult" class="text-zinc-300">总分 {{ optimizeResult.total_score ?? '-' }}</span>
              <button class="hard-button py-1" type="button" @click="toggleSection('result')">{{ collapseLabel('result') }}</button>
            </div>
          </div>
          <div v-if="optimizeResult && !collapsed.result" class="space-y-4 p-4">
            <div class="grid gap-3 md:grid-cols-2">
              <div class="metric-box">
                <span>匹配类型</span>
                <strong class="text-base">{{ matchTypeLabel(optimizeResult.match_type) }}</strong>
              </div>
              <div class="metric-box">
                <span>总分</span>
                <strong>{{ optimizeResult.total_score ?? '-' }}</strong>
              </div>
            </div>

            <div class="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
              <article
                v-for="(item, index) in comboItems(optimizeResult)"
                :key="diskId(item, index)"
                class="disk-card"
                :class="[isEmptyComboSlot(item) ? 'opacity-70' : rarityClass(item)]"
              >
                <div v-if="isEmptyComboSlot(item)" class="flex min-h-[180px] flex-col items-center justify-center rounded-sm border-2 border-dashed border-zinc-700 bg-zinc-950 p-4 text-center">
                  <p class="font-mono text-xs font-black text-[#f6ce00]">{{ comboSlotLabel(item, index) }}</p>
                  <h3 class="mt-2 text-base font-black text-zinc-300">留空</h3>
                  <p class="mt-2 max-w-[220px] font-mono text-xs font-bold text-zinc-500">该位置暂无可用驱动盘，不参与总分和套装统计。</p>
                </div>
                <template v-else>
                <div class="flex gap-3">
                  <div class="disk-vinyl h-20 w-20" :style="diskStyle(item)"></div>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-start justify-between gap-2">
                      <div class="min-w-0">
                        <p class="truncate font-mono text-xs font-black text-[#f6ce00]">{{ comboSlotLabel(item, index) }}</p>
                        <h3 class="truncate text-sm font-black">
                          {{ item.set_name || '未知套装' }}
                          <span class="font-mono" :class="levelClass(item)">+{{ item.level ?? item.upgrade_level ?? 0 }}</span>
                        </h3>
                      </div>
                      <div class="shrink-0 text-right font-mono text-xs font-black">
                        <p class="cursor-help text-[#f6ce00]" :title="scoreFormulaTitle(item, comboScore(optimizeResult, index))">
                          得分 {{ displayScore(comboScore(optimizeResult, index)) }}
                        </p>
                      </div>
                    </div>
                    <p class="mt-1 truncate font-mono text-xs font-black text-zinc-300">{{ item.slot || index + 1 }} 号位驱动盘</p>
                    <p class="mt-2 truncate font-mono text-xs text-zinc-400">主词条：{{ statName(item.main_stat) }} {{ statValue(item.main_stat) }}</p>
                    <p class="mt-2 font-mono text-[11px] font-bold text-zinc-500">{{ warehouseLabel(item) }}</p>
                  </div>
                </div>
                <div class="mt-3 border-t-2 border-zinc-800 pt-3">
                  <p class="mb-2 font-mono text-xs font-black text-zinc-500">副词条</p>
                  <div v-if="subStatsOf(item).length" class="grid grid-cols-2 gap-2">
                    <span
                      v-for="sub in subStatsOf(item)"
                      :key="`${item.id || index}-${statName(sub)}-${statValue(sub)}`"
                      class="rounded-sm border-2 bg-zinc-900 px-2 py-1 font-mono text-[11px] font-black text-zinc-300"
                      :class="isEffectiveSubStat(sub) ? 'effective-stat-chip' : 'border-zinc-800'"
                      :title="subStatTitle(sub)"
                    >
                      {{ statName(sub) }} {{ statValue(sub) }}
                      <span class="text-[#f6ce00]">· +{{ statUpgradeCount(sub) }}</span>
                    </span>
                  </div>
                  <p v-else class="font-mono text-xs font-bold text-zinc-600">暂无副词条</p>
                </div>
                <button class="mt-3 hard-button w-full py-2" type="button" @click="locateDisk(item)">
                  定位到游戏中（预留）
                </button>
                </template>
              </article>
            </div>
          </div>
        </div>

        <div v-if="hasRunPromising" class="panel">
          <div class="panel-title flex items-center justify-between gap-3">
            <span>培养推荐</span>
            <button class="hard-button py-1" type="button" @click="toggleSection('promising')">{{ collapseLabel('promising') }}</button>
          </div>
          <div v-if="!collapsed.promising" class="space-y-4 p-4">
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

            <div class="slot-tabs">
              <button
                v-for="slot in [1, 2, 3, 4, 5, 6]"
                :key="`promising-tab-${slot}`"
                class="slot-tab"
                :class="{ 'slot-tab-active': promisingSlot === slot }"
                type="button"
                @click="promisingSlot = slot"
              >
                <span>{{ slot }} 号位</span>
                <strong>{{ promisingSlotGroups.find((group) => group.slot === slot)?.items.length || 0 }}</strong>
              </button>
            </div>

            <div class="max-h-[720px] space-y-3 overflow-auto pr-1">
              <article v-for="(item, index) in activePromisingGroup.items" :key="diskId(item.disk, index)" class="disk-card" :class="rarityClass(item.disk)">
                <div class="flex gap-3">
                  <div class="disk-vinyl h-20 w-20" :style="diskStyle(item.disk)"></div>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-start justify-between gap-2">
                      <div class="min-w-0">
                        <p class="truncate font-mono text-xs font-black text-[#f6ce00]">{{ rankLabel(item.rank) }}</p>
                        <h3 class="truncate text-sm font-black">
                          {{ item.disk?.set_name || '未知套装' }}
                          <span class="font-mono" :class="levelClass(item.disk)">+{{ item.disk?.level ?? item.disk?.upgrade_level ?? 0 }}</span>
                        </h3>
                      </div>
                      <div class="shrink-0 text-right font-mono text-xs font-black">
                        <p class="cursor-help text-[#f6ce00]" :title="potentialFormulaTitle(item)">潜力 {{ displayScore(item.potential_score) }}</p>
                        <p class="cursor-help text-zinc-500" :title="scoreFormulaTitle(item.disk, item.current_score)">当前 {{ displayScore(item.current_score) }}</p>
                      </div>
                    </div>
                    <p class="mt-1 truncate font-mono text-xs font-black text-zinc-300">{{ item.disk?.slot || '-' }} 号位驱动盘</p>
                    <p class="mt-2 truncate font-mono text-xs text-zinc-400">主词条：{{ statName(item.disk?.main_stat) }} {{ statValue(item.disk?.main_stat) }}</p>
                    <p class="mt-2 font-mono text-[11px] font-bold text-zinc-500">仓库：{{ warehouseLabel(item.disk) }}</p>
                  </div>
                </div>
                <div class="mt-3 grid grid-cols-2 gap-2">
                  <span
                    v-for="sub in subStatsOf(item.disk)"
                    :key="`${item.disk?.id || index}-${statName(sub)}-${statValue(sub)}`"
                    class="rounded-sm border-2 bg-zinc-900 px-2 py-1 font-mono text-[11px] font-black text-zinc-300"
                    :class="isEffectiveSubStat(sub) ? 'effective-stat-chip' : 'border-zinc-800'"
                    :title="subStatTitle(sub)"
                  >
                    {{ statName(sub) }} {{ statValue(sub) }}
                    <span class="text-[#f6ce00]">· +{{ statUpgradeCount(sub) }}</span>
                  </span>
                </div>
                <div class="mt-3 flex flex-wrap gap-2">
                  <span v-for="reason in item.reasons || []" :key="reason" class="reason-chip">{{ formatReason(reason) }}</span>
                </div>
                <button class="mt-3 hard-button w-full py-2" type="button" @click="locateDisk(item.disk)">
                  定位到游戏中（预留）
                </button>
              </article>
              <div v-if="promisingResults.length && !activePromisingGroup.items.length" class="empty-state">
                当前 {{ promisingSlot }} 号位暂无符合条件的胚子。
              </div>
              <div v-if="!promisingResults.length" class="empty-state">尚未运行胚子推荐。</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
