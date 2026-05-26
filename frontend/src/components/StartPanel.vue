<template>
  <div class="layout layout-centered">
    <section class="panel panel-form panel-centered">
      <header class="panel-head">
        <div class="logo"><span>AI</span></div>
        <div><h1>深度研究助手</h1><p>结合多轮智能检索与总结，实时呈现洞见与引用。</p></div>
      </header>

      <form class="form" @submit.prevent="handleSubmit">
        <label class="field">
          <span>研究主题</span>
          <textarea v-model="form.topic" placeholder="例如：探索多模态模型..." rows="4" required></textarea>
        </label>
        <section class="options">
          <label class="field option">
            <span>搜索引擎</span>
            <select v-model="form.searchApi">
              <option value="">沿用后端配置</option>
              <option v-for="opt in searchOptions" :key="opt" :value="opt">{{ opt }}</option>
            </select>
          </label>
        </section>
        <div class="form-actions">
          <button class="submit" type="submit" :disabled="loading">
            <span class="submit-label">{{ loading ? "研究进行中..." : "开始研究" }}</span>
          </button>
          <button v-if="loading" type="button" class="secondary-btn" @click="cancelResearch">取消研究</button>
        </div>
      </form>
      <p v-if="error" class="error-chip">{{ error }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useResearchState } from '../composables/useResearchState';
const { form, loading, error, handleSubmit, cancelResearch } = useResearchState();
const searchOptions = ["advanced", "duckduckgo", "tavily", "perplexity", "searxng"];
</script>

<style scoped>
.layout-centered { width: 100%; max-width: 600px; display: flex; justify-content: center; z-index: 1; }
.panel { background: rgba(255, 255, 255, 0.95); padding: 40px; border-radius: 20px; box-shadow: 0 32px 64px rgba(15, 23, 42, 0.15); backdrop-filter: blur(8px); }
.panel-head { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.logo { width: 52px; height: 52px; display: grid; place-items: center; border-radius: 16px; background: linear-gradient(135deg, #2563eb, #7c3aed); color: white; font-weight: bold; }
.form { display: flex; flex-direction: column; gap: 18px; }
.field { display: flex; flex-direction: column; gap: 10px; font-weight: 600; color: #475569; }
textarea, select { padding: 14px; border-radius: 16px; border: 1px solid rgba(148, 163, 184, 0.35); outline: none; transition: border-color 0.2s; }
textarea:focus, select:focus { border-color: #2563eb; }
.submit { padding: 12px 24px; border-radius: 16px; border: none; background: linear-gradient(135deg, #2563eb, #7c3aed); color: white; cursor: pointer; font-weight: 600; }
.submit:disabled { opacity: 0.7; }
.secondary-btn { padding: 10px 18px; border-radius: 14px; background: rgba(148, 163, 184, 0.12); border: 1px solid rgba(148, 163, 184, 0.28); cursor: pointer; }
.error-chip { background: rgba(248, 113, 113, 0.12); color: #b91c1c; padding: 10px; border-radius: 14px; }
</style>