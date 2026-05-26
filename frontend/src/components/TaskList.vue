<template>
  <aside class="tasks-list">
    <h3>任务清单</h3>
    <ul>
      <li v-for="task in todoTasks" :key="task.id"
          :class="['task-item', { active: task.id === activeTaskId, completed: task.status === 'completed' }]">
        <button type="button" class="task-button" @click="activeTaskId = task.id">
          <span class="task-title">{{ task.title }}</span>
          <span class="task-status" :class="task.status">{{ TASK_STATUS_LABEL[task.status] || task.status }}</span>
        </button>
      </li>
    </ul>
  </aside>
</template>

<script setup lang="ts">
import { useResearchState } from '../composables/useResearchState';
const { todoTasks, activeTaskId } = useResearchState();
const TASK_STATUS_LABEL: Record<string, string> = { pending: "待执行", in_progress: "进行中", completed: "已完成", skipped: "已跳过" };
</script>

<style scoped>
.tasks-list { background: rgba(255, 255, 255, 0.92); border: 1px solid #cbd5e1; border-radius: 18px; padding: 18px; }
ul { list-style: none; padding: 0; display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.task-item { border-radius: 12px; border: 1px solid transparent; transition: all 0.2s; }
.task-item.active { background: rgba(224, 231, 255, 0.5); border-color: rgba(129, 140, 248, 0.5); }
.task-item.completed { background: rgba(191, 219, 254, 0.28); }
.task-button { width: 100%; text-align: left; background: none; border: none; padding: 12px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
.task-status { font-size: 12px; padding: 4px 8px; border-radius: 12px; background: #e2e8f0; }
.task-status.in_progress { background: #c7d2fe; color: #312e81; }
.task-status.completed { background: #bbf7d0; color: #166534; }
</style>