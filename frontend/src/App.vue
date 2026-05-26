<template>
  <main class="app-shell" :class="{ expanded: isExpanded }">
    <div class="aurora" aria-hidden="true"><span></span><span></span><span></span></div>

    <StartPanel v-if="!isExpanded" />

    <div v-else class="layout-fullscreen">
      <ResearchSidebar />

      <section class="panel-result">
        <div
          v-if="(loading || progressLogs.length) && !todoTasks.length && !reportMarkdown"
          class="progress-block"
        >
          <h3>研究进度</h3>
          <p class="muted" v-if="loading">正在运行中，请稍候…</p>
          <ul class="progress-list">
            <li v-for="(log, index) in progressLogs" :key="index">{{ log }}</li>
          </ul>
        </div>
        <div class="tasks-section" v-if="todoTasks.length">
          <TaskList />
          <TaskDetail />
        </div>

        <div v-if="reportMarkdown" class="report-block" :class="{ 'block-highlight': reportHighlight }">
          <h3>最终报告</h3>
          <pre class="block-pre">{{ reportMarkdown }}</pre>
        </div>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onBeforeUnmount } from 'vue';
import { useResearchState } from './composables/useResearchState';

// 引入拆分好的 UI 组件
import StartPanel from './components/StartPanel.vue';
import ResearchSidebar from './components/ResearchSidebar.vue';
import TaskList from './components/TaskList.vue';
import TaskDetail from './components/TaskDetail.vue';

// 只需从状态中心提取 App.vue 外壳所需的控制变量
const {
  isExpanded,
  todoTasks,
  reportMarkdown,
  reportHighlight,
  currentController,
  loading,
  progressLogs,
} = useResearchState();

// 处理组件卸载时的网络中止
onBeforeUnmount(() => {
  if (currentController) {
    currentController.abort();
  }
});
</script>

<style scoped>
.layout-fullscreen { display: flex; width: 100%; height: 100vh; z-index: 1; }
.panel-result { flex: 1; padding: 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 20px; }
.tasks-section { display: grid; grid-template-columns: 280px 1fr; gap: 20px; align-items: start; }
.report-block { background: white; padding: 24px; border-radius: 18px; border: 1px solid #cbd5e1; }
.block-pre { font-family: monospace; white-space: pre-wrap; background: #f8fafc; padding: 16px; border-radius: 14px; }
.progress-block {
  background: white;
  padding: 20px;
  border-radius: 18px;
  border: 1px solid #cbd5e1;
}
.progress-list {
  margin: 12px 0 0;
  padding-left: 18px;
  color: #334155;
}
.muted { color: #64748b; font-size: 13px; margin-top: 6px; }
</style>