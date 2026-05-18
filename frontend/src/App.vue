<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import LogView from './views/LogView.vue';
import MatchView from './views/MatchView.vue';
import ScanView from './views/ScanView.vue';

const activeTab = ref('scan');
const logs = ref([]);
const environment = ref({});

const visibleLogs = computed(() => logs.value.slice(0, 300));

function nowText() {
  return new Date().toLocaleString('zh-CN', { hour12: false });
}

function compactDetail(value) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function addLog(level, message, detail = '') {
  logs.value = [
    {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      time: nowText(),
      level,
      message,
      detail: compactDetail(detail),
    },
    ...logs.value,
  ].slice(0, 500);
}

function refreshEnvironment() {
  const api = window?.pywebview?.api;
  environment.value = {
    后端桥接: api ? '已连接' : '未连接',
    当前页面: activeTab.value === 'scan' ? '扫描' : activeTab.value === 'match' ? '配装' : '日志',
    页面地址: window.location.href,
    浏览器内核: navigator.userAgent,
    语言: navigator.language || '未知',
    窗口尺寸: `${window.innerWidth} x ${window.innerHeight}`,
    更新时间: nowText(),
  };
  addLog('信息', '运行信息已刷新。', environment.value);
}

function clearLogs() {
  logs.value = [];
  addLog('信息', '日志已清空。');
}

function handleMaaProgress(event) {
  addLog('事件', event?.detail?.message || '收到扫描进度事件。', event?.detail);
}

function handleMaaComplete(event) {
  addLog('事件', '扫描任务完成。', event?.detail);
}

function handleMaaError(event) {
  addLog('错误', event?.detail?.error || event?.detail?.message || '扫描任务出错。', event?.detail);
}

function openLogs() {
  activeTab.value = 'logs';
  refreshEnvironment();
}

onMounted(() => {
  window.addEventListener('maa-progress', handleMaaProgress);
  window.addEventListener('maa-complete', handleMaaComplete);
  window.addEventListener('maa-error', handleMaaError);
  window.addEventListener('resize', refreshEnvironment);
  refreshEnvironment();
  addLog('信息', '前端界面已启动。');
});

onBeforeUnmount(() => {
  window.removeEventListener('maa-progress', handleMaaProgress);
  window.removeEventListener('maa-complete', handleMaaComplete);
  window.removeEventListener('maa-error', handleMaaError);
  window.removeEventListener('resize', refreshEnvironment);
});
</script>

<template>
  <div class="min-h-screen overflow-x-hidden bg-zinc-950 text-zinc-100">
    <header class="border-b-4 border-[#f6ce00] bg-zinc-900">
      <div class="mx-auto flex max-w-7xl flex-col items-stretch gap-4 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <button class="min-w-0 text-left transition duration-100 hover:-translate-y-0.5" type="button" title="查看运行日志" @click="openLogs">
          <p class="font-mono text-xs font-black tracking-widest text-[#f6ce00]">绝区零驱动盘助手</p>
          <h1 class="break-words font-display text-2xl font-black leading-tight">驱动盘作战控制台</h1>
        </button>
        <nav class="grid grid-cols-3 gap-2 sm:flex sm:shrink-0">
          <button
            class="hard-button"
            :class="{ 'hard-button-active': activeTab === 'scan' }"
            type="button"
            @click="activeTab = 'scan'"
          >
            扫描
          </button>
          <button
            class="hard-button"
            :class="{ 'hard-button-active': activeTab === 'match' }"
            type="button"
            @click="activeTab = 'match'"
          >
            配装
          </button>
          <button
            class="hard-button"
            :class="{ 'hard-button-active': activeTab === 'logs' }"
            type="button"
            @click="activeTab = 'logs'; refreshEnvironment()"
          >
            日志
          </button>
        </nav>
      </div>
    </header>

    <main>
      <ScanView v-if="activeTab === 'scan'" />
      <MatchView v-else-if="activeTab === 'match'" />
      <LogView v-else :logs="visibleLogs" :environment="environment" @clear="clearLogs" @refresh="refreshEnvironment" />
    </main>
  </div>
</template>
