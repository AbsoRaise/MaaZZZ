<script setup>
defineProps({
  logs: {
    type: Array,
    default: () => [],
  },
  environment: {
    type: Object,
    default: () => ({}),
  },
});

const emit = defineEmits(['clear', 'refresh']);

function levelClass(level) {
  if (level === '错误') return 'border-red-500 text-red-200';
  if (level === '警告') return 'border-amber-400 text-amber-200';
  if (level === '事件') return 'border-[#f6ce00] text-[#f6ce00]';
  return 'border-zinc-700 text-zinc-300';
}
</script>

<template>
  <section class="mx-auto grid max-w-7xl gap-5 px-4 py-6 lg:grid-cols-[minmax(260px,340px)_minmax(0,1fr)]">
    <aside class="min-w-0 space-y-5">
      <div class="panel shadow-hard">
        <div class="panel-title">日志控制</div>
        <div class="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-1">
          <button class="hard-button hard-button-active w-full whitespace-normal" type="button" @click="emit('refresh')">
            刷新运行信息
          </button>
          <button class="hard-button w-full whitespace-normal" type="button" @click="emit('clear')">
            清空当前日志
          </button>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">运行信息</div>
        <div class="grid gap-2 p-4 sm:grid-cols-2 lg:grid-cols-1">
          <div v-for="(value, key) in environment" :key="key" class="debug-info-box">
            <span>{{ key }}</span>
            <strong>{{ value }}</strong>
          </div>
        </div>
      </div>
    </aside>

    <div class="panel min-w-0">
      <div class="panel-title flex items-center justify-between gap-3">
        <span>运行日志</span>
        <span class="text-zinc-400">{{ logs.length }} 条</span>
      </div>
      <div class="max-h-[calc(100vh-180px)] min-w-0 space-y-2 overflow-auto p-4">
        <article
          v-for="item in logs"
          :key="item.id"
          class="min-w-0 rounded-sm border-2 bg-zinc-950 p-3 font-mono text-xs font-bold"
          :class="levelClass(item.level)"
        >
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span class="font-black">{{ item.level }}</span>
            <span class="text-zinc-500">{{ item.time }}</span>
          </div>
          <p class="break-all text-zinc-100 sm:break-words">{{ item.message }}</p>
          <pre v-if="item.detail" class="debug-pre">{{ item.detail }}</pre>
        </article>

        <div v-if="!logs.length" class="empty-state">暂无运行日志</div>
      </div>
    </div>
  </section>
</template>
