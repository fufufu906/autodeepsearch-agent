<template>
  <article class="task-detail" v-if="task">
    <header class="task-header">
      <div>
        <h3>{{ task.title }}</h3>
        <p class="muted">{{ task.intent }}</p>
      </div>
    </header>

    <section class="sources-block" :class="{ 'block-highlight': sourcesHighlight }">
      <h3>最新来源</h3>
      <ul v-if="task.sourceItems.length" class="sources-list">
        <li v-for="(item, index) in task.sourceItems" :key="index" class="source-item">
          <a class="source-link" :href="item.url" target="_blank">{{ item.title || item.url }}</a>
        </li>
      </ul>
      <p v-else class="muted">暂无可用来源</p>
    </section>

    <section class="summary-block" :class="{ 'block-highlight': summaryHighlight }">
      <h3>任务总结</h3>
      <pre class="block-pre">{{ task.summary || "暂无可用信息" }}</pre>
    </section>
  </article>
</template>

<script setup lang="ts">
import { useResearchState } from '../composables/useResearchState';
import { computed } from 'vue';

const { currentTask, sourcesHighlight, summaryHighlight } = useResearchState();
// 使用 computed 维持响应式
const task = computed(() => currentTask.value);
</script>

<style scoped>
.task-detail { background: rgba(255, 255, 255, 0.94); border: 1px solid #cbd5e1; border-radius: 18px; padding: 22px; display: flex; flex-direction: column; gap: 18px; }
.task-header h3 { margin: 0; font-size: 18px; }
.muted { color: #64748b; font-size: 13px; margin-top: 6px; }
.sources-block, .summary-block { padding: 18px; border-radius: 18px; border: 1px solid #e2e8f0; background: white; }
.block-pre { font-family: monospace; font-size: 13px; white-space: pre-wrap; background: #f8fafc; padding: 16px; border-radius: 14px; max-height: 360px; overflow-y: auto; }
.source-link { color: #2563eb; text-decoration: none; }
.block-highlight { animation: glow 1.2s ease; }
@keyframes glow { 0% { box-shadow: 0 0 0 rgba(59, 130, 246, 0.3); } 100% { box-shadow: none; } }
</style>