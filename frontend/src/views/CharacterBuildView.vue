<script setup>
import { computed, onMounted, ref, watch } from 'vue';

const DEFAULT_METADATA = {
  disk_types: ['极地重金属', '啄木鸟电音', '震星迪斯科', '激素朋克', '獠牙重金属', '河豚电音', '自由蓝调'],
  main_stats: ['生命值', '攻击力', '防御力', '暴击率', '暴击伤害', '异常精通', '穿透率', '能量自动回复', '冲击力', '冰属性伤害'],
  sub_stats: ['生命值', '攻击力', '防御力', '暴击率', '暴击伤害', '异常精通', '穿透值'],
};

const builds = ref({});
const metadata = ref(DEFAULT_METADATA);
const selectedName = ref('');
const newCharacterName = ref('');
const draft = ref(emptyBuild());
const isLoading = ref(false);
const isSaving = ref(false);
const infoText = ref('');
const errorText = ref('');

const characterNames = computed(() => Object.keys(builds.value).sort((a, b) => a.localeCompare(b, 'zh-CN')));
const statOptions = computed(() => {
  const values = new Set([...(metadata.value.main_stats || []), ...(metadata.value.sub_stats || [])]);
  draft.value.weights.forEach((item) => {
    if (item.name) values.add(item.name);
  });
  return [...values].filter(Boolean).sort((a, b) => a.localeCompare(b, 'zh-CN'));
});
const setOptions = computed(() => {
  const values = new Set(metadata.value.disk_types || []);
  Object.values(builds.value).forEach((build) => {
    const sets = build?.preferred_sets || {};
    if (sets.target_set_4) values.add(sets.target_set_4);
    if (sets.target_set_2) values.add(sets.target_set_2);
    (sets.alternatives || []).forEach((item) => {
      if (item?.target_set_4) values.add(item.target_set_4);
      if (item?.target_set_2) values.add(item.target_set_2);
    });
  });
  return [...values].filter(Boolean).sort((a, b) => a.localeCompare(b, 'zh-CN'));
});
const canSave = computed(() => Boolean(selectedName.value.trim()) && !isSaving.value);

watch(selectedName, (name) => {
  draft.value = buildToDraft(builds.value[name]);
  infoText.value = '';
  errorText.value = '';
});

function getApi() {
  return window?.pywebview?.api || null;
}

function waitForApi(timeoutMs = 3000) {
  const existing = getApi();
  if (existing) return Promise.resolve(existing);
  return new Promise((resolve) => {
    let done = false;
    const startedAt = Date.now();
    const finish = (api) => {
      if (done) return;
      done = true;
      window.removeEventListener('pywebviewready', handleReady);
      resolve(api || null);
    };
    const handleReady = () => finish(getApi());
    const poll = () => {
      const api = getApi();
      if (api || Date.now() - startedAt >= timeoutMs) return finish(api);
      window.setTimeout(poll, 80);
    };
    window.addEventListener('pywebviewready', handleReady, { once: true });
    poll();
  });
}

function unwrapResponse(response) {
  if (!response || typeof response !== 'object' || !Object.prototype.hasOwnProperty.call(response, 'success')) return response;
  if (response.success === false) throw new Error(response.error || '后端操作失败');
  return response.data;
}

function errorMessageOf(error) {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return error?.message || error?.error || '未知错误';
}

async function callApi(name, ...args) {
  const api = getApi();
  if (api?.[name]) return unwrapResponse(await api[name](...args));
  return unwrapResponse(await mockApi(name, ...args));
}

async function mockApi(name, ...args) {
  await new Promise((resolve) => window.setTimeout(resolve, 120));
  if (name === 'get_character_builds') {
    return {
      '艾莲·乔': {
        weights: { 暴击率: 1, 暴击伤害: 1, '攻击力%': 0.8, 穿透值: 0.45 },
        preferred_main_stats: { 4: ['暴击率', '暴击伤害'], 5: ['冰属性伤害', '攻击力%'], 6: ['攻击力%'] },
        preferred_sets: { target_set_4: '极地重金属', target_set_2: '啄木鸟电音', alternatives: [] },
      },
    };
  }
  if (name === 'get_disk_metadata') return DEFAULT_METADATA;
  if (name === 'save_character_build') return args[1];
  return null;
}

function emptyBuild() {
  return {
    weights: [{ name: '', value: 1 }],
    preferred_main_stats: { 4: [], 5: [], 6: [] },
    preferred_sets: {
      target_set_4: '',
      target_set_2: '',
      alternatives: [],
    },
  };
}

function buildToDraft(build) {
  if (!build || typeof build !== 'object') return emptyBuild();
  const weights = Object.entries(build.weights || {}).map(([name, value]) => ({ name, value: Number(value) || 0 }));
  const alternatives = Array.isArray(build.preferred_sets?.alternatives)
    ? build.preferred_sets.alternatives.map((item) => ({
        target_set_4: String(item?.target_set_4 || ''),
        target_set_2: String(item?.target_set_2 || ''),
        note: String(item?.note || ''),
      }))
    : [];
  return {
    weights: weights.length ? weights : [{ name: '', value: 1 }],
    preferred_main_stats: {
      4: [...normalizeMainStats(build.preferred_main_stats?.[4] ?? build.preferred_main_stats?.['4'])],
      5: [...normalizeMainStats(build.preferred_main_stats?.[5] ?? build.preferred_main_stats?.['5'])],
      6: [...normalizeMainStats(build.preferred_main_stats?.[6] ?? build.preferred_main_stats?.['6'])],
    },
    preferred_sets: {
      target_set_4: String(build.preferred_sets?.target_set_4 || ''),
      target_set_2: String(build.preferred_sets?.target_set_2 || ''),
      alternatives,
    },
  };
}

function normalizeMainStats(value) {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  if (!value) return [];
  return String(value).split(/[，,]/).map((item) => item.trim()).filter(Boolean);
}

function draftToBuild() {
  return {
    weights: Object.fromEntries(
      draft.value.weights
        .map((item) => [String(item.name || '').trim(), Number(item.value) || 0])
        .filter(([name]) => name),
    ),
    preferred_main_stats: {
      4: [...draft.value.preferred_main_stats[4]],
      5: [...draft.value.preferred_main_stats[5]],
      6: [...draft.value.preferred_main_stats[6]],
    },
    preferred_sets: {
      target_set_4: draft.value.preferred_sets.target_set_4.trim(),
      target_set_2: draft.value.preferred_sets.target_set_2.trim(),
      alternatives: draft.value.preferred_sets.alternatives
        .map((item) => ({
          target_set_4: String(item.target_set_4 || '').trim(),
          target_set_2: String(item.target_set_2 || '').trim(),
          note: String(item.note || '').trim(),
        }))
        .filter((item) => item.target_set_4 || item.target_set_2 || item.note),
    },
  };
}

function addWeight() {
  draft.value.weights.push({ name: '', value: 1 });
}

function removeWeight(index) {
  draft.value.weights.splice(index, 1);
  if (!draft.value.weights.length) addWeight();
}

function addAlternative() {
  draft.value.preferred_sets.alternatives.push({ target_set_4: '', target_set_2: '', note: '' });
}

function removeAlternative(index) {
  draft.value.preferred_sets.alternatives.splice(index, 1);
}

function isMainStatSelected(slot, stat) {
  return draft.value.preferred_main_stats[slot].includes(stat);
}

function toggleMainStat(slot, stat) {
  const stats = draft.value.preferred_main_stats[slot];
  const index = stats.indexOf(stat);
  if (index >= 0) stats.splice(index, 1);
  else stats.push(stat);
}

function createCharacter() {
  const name = newCharacterName.value.trim();
  if (!name) return;
  selectedName.value = name;
  builds.value = { ...builds.value, [name]: draftToBuild() };
  draft.value = emptyBuild();
  newCharacterName.value = '';
}

async function loadData() {
  isLoading.value = true;
  errorText.value = '';
  try {
    const [buildPayload, metadataPayload] = await Promise.all([
      callApi('get_character_builds'),
      callApi('get_disk_metadata'),
    ]);
    builds.value = buildPayload && typeof buildPayload === 'object' ? buildPayload : {};
    metadata.value = { ...DEFAULT_METADATA, ...(metadataPayload || {}) };
    selectedName.value = selectedName.value && builds.value[selectedName.value] ? selectedName.value : characterNames.value[0] || '';
    draft.value = buildToDraft(builds.value[selectedName.value]);
  } catch (error) {
    errorText.value = errorMessageOf(error);
  } finally {
    isLoading.value = false;
  }
}

async function saveBuild() {
  if (!canSave.value) return;
  isSaving.value = true;
  errorText.value = '';
  try {
    const config = draftToBuild();
    const saved = await callApi('save_character_build', selectedName.value, config);
    builds.value = { ...builds.value, [selectedName.value]: saved || config };
    infoText.value = `已保存 ${selectedName.value}。`;
    window.dispatchEvent(new CustomEvent('app-log', { detail: { level: '信息', message: infoText.value, detail: config } }));
  } catch (error) {
    errorText.value = errorMessageOf(error);
  } finally {
    isSaving.value = false;
  }
}

onMounted(async () => {
  await waitForApi();
  await loadData();
});
</script>

<template>
  <section class="mx-auto grid max-w-7xl gap-5 px-4 py-6 lg:grid-cols-[320px_minmax(0,1fr)]">
    <aside class="space-y-5">
      <div class="panel shadow-hard">
        <div class="panel-title">角色配置</div>
        <div class="space-y-3 p-4">
          <div class="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
            <input v-model="newCharacterName" class="hard-input min-w-0" type="text" placeholder="新角色名称" />
            <button class="hard-button" type="button" @click="createCharacter">新增</button>
          </div>
          <button class="hard-button w-full" type="button" :disabled="isLoading" @click="loadData">
            {{ isLoading ? '读取中' : '重新读取' }}
          </button>
          <p v-if="infoText" class="notice-box border-[#f6ce00] text-[#f6ce00]">{{ infoText }}</p>
          <p v-if="errorText" class="notice-box border-red-500 text-red-200">{{ errorText }}</p>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title flex items-center justify-between gap-3">
          <span>角色列表</span>
          <span class="text-zinc-400">{{ characterNames.length }}</span>
        </div>
        <div class="max-h-[calc(100vh-290px)] space-y-2 overflow-auto p-4">
          <button
            v-for="name in characterNames"
            :key="name"
            class="w-full rounded-sm border-2 px-3 py-2 text-left font-mono text-xs font-black transition duration-100 hover:border-[#f6ce00]"
            :class="selectedName === name ? 'border-[#f6ce00] bg-[#f6ce00] text-zinc-950' : 'border-zinc-800 bg-zinc-950 text-zinc-200'"
            type="button"
            @click="selectedName = name"
          >
            {{ name }}
          </button>
          <div v-if="!characterNames.length" class="empty-state">暂无角色配置</div>
        </div>
      </div>
    </aside>

    <div class="space-y-5">
      <div class="panel">
        <div class="panel-title flex items-center justify-between gap-3">
          <span>{{ selectedName || '未选择角色' }}</span>
          <button class="hard-button hard-button-active py-1" type="button" :disabled="!canSave" @click="saveBuild">
            {{ isSaving ? '保存中' : '保存配置' }}
          </button>
        </div>

        <div class="grid gap-5 p-4 xl:grid-cols-2">
          <div class="space-y-5">
            <div class="rounded-sm border-2 border-zinc-800 bg-zinc-950 p-3">
              <div class="mb-3 flex items-center justify-between gap-3">
                <p class="field-label">副属性权重</p>
                <button class="hard-button py-1" type="button" @click="addWeight">新增权重</button>
              </div>
              <div class="space-y-2">
                <div v-for="(item, index) in draft.weights" :key="index" class="grid grid-cols-[minmax(0,1fr)_96px_auto] gap-2">
                  <input v-model="item.name" class="hard-input min-w-0" list="stat-options" type="text" placeholder="属性名" />
                  <input v-model.number="item.value" class="hard-input" type="number" step="0.05" />
                  <button class="hard-button px-3" type="button" @click="removeWeight(index)">删</button>
                </div>
              </div>
            </div>

            <div class="rounded-sm border-2 border-zinc-800 bg-zinc-950 p-3">
              <p class="field-label mb-3">套装目标</p>
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
            </div>
          </div>

          <div class="space-y-5">
            <div class="rounded-sm border-2 border-zinc-800 bg-zinc-950 p-3">
              <p class="field-label mb-3">4/5/6 号位推荐主属性</p>
              <div class="space-y-3">
                <div v-for="slot in [4, 5, 6]" :key="slot">
                  <p class="mb-2 font-mono text-xs font-black text-zinc-300">{{ slot }} 号位</p>
                  <div class="max-h-36 overflow-auto rounded-sm border-2 border-zinc-800 bg-zinc-900 p-2">
                    <button
                      v-for="stat in statOptions"
                      :key="`${slot}-${stat}`"
                      class="stat-choice"
                      :class="{ 'stat-choice-active': isMainStatSelected(slot, stat) }"
                      type="button"
                      @click="toggleMainStat(slot, stat)"
                    >
                      {{ stat }}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div class="rounded-sm border-2 border-zinc-800 bg-zinc-950 p-3">
              <div class="mb-3 flex items-center justify-between gap-3">
                <p class="field-label">备选套装</p>
                <button class="hard-button py-1" type="button" @click="addAlternative">新增备选</button>
              </div>
              <div class="space-y-2">
                <div v-for="(item, index) in draft.preferred_sets.alternatives" :key="index" class="grid gap-2 rounded-sm border-2 border-zinc-800 bg-zinc-900 p-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
                  <input v-model="item.target_set_4" class="hard-input min-w-0" list="set-options" type="text" placeholder="四件套" />
                  <input v-model="item.target_set_2" class="hard-input min-w-0" list="set-options" type="text" placeholder="二件套" />
                  <input v-model="item.note" class="hard-input min-w-0" type="text" placeholder="备注" />
                  <button class="hard-button px-3" type="button" @click="removeAlternative(index)">删</button>
                </div>
                <p v-if="!draft.preferred_sets.alternatives.length" class="font-mono text-xs font-bold text-zinc-500">暂无备选套装。</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <datalist id="stat-options">
      <option v-for="stat in statOptions" :key="stat" :value="stat" />
    </datalist>
    <datalist id="set-options">
      <option v-for="setName in setOptions" :key="setName" :value="setName" />
    </datalist>
  </section>
</template>
