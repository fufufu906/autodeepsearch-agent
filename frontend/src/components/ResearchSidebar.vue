<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <button class="back-btn" @click="goBack" :disabled="loading">← 返回</button>
      <h2>🔍 深度研究助手</h2>
    </div>

    <div class="research-info">
      <div class="info-item">
        <label>研究主题</label>
        <p class="topic-display">{{ form.topic }}</p>
      </div>
      <div class="info-item" v-if="totalTasks > 0">
        <label>研究进度</label>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${(completedTasks / totalTasks) * 100}%` }"></div>
        </div>
        <p class="progress-text">{{ completedTasks }} / {{ totalTasks }} 任务完成</p>
      </div>
    </div>

    <div class="sidebar-actions">
      <button class="new-research-btn" @click="startNewResearch">开始新研究</button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { useResearchState } from '../composables/useResearchState';
const { form, loading, totalTasks, completedTasks, goBack, startNewResearch } = useResearchState();
</script>

<style scoped>
.sidebar { width: 320px; height: 100vh; background: rgba(255, 255, 255, 0.98); border-right: 1px solid rgba(148, 163, 184, 0.2); padding: 32px 24px; display: flex; flex-direction: column; gap: 24px; z-index: 2; }
.sidebar-header h2 { font-size: 20px; margin: 16px 0 0; }
.back-btn { background: transparent; border: 1px solid #cbd5e1; padding: 6px 12px; border-radius: 8px; cursor: pointer; }
.info-item { display: flex; flex-direction: column; gap: 8px; }
.info-item label { font-size: 12px; font-weight: 600; color: #64748b; }
.topic-display { padding: 12px; background: rgba(59, 130, 246, 0.05); border-left: 3px solid #3b82f6; border-radius: 8px; font-size: 14px; }
.progress-bar { width: 100%; height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #3b82f6, #8b5cf6); transition: width 0.3s; }
.new-research-btn { padding: 12px; background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: white; border: none; border-radius: 12px; cursor: pointer; font-weight: bold; }
</style>