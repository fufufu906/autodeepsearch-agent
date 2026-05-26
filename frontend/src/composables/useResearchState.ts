// src1/composables/useResearchState.ts
import { ref, reactive, computed } from "vue";
import type { TodoTaskView, SourceItem } from "../types";
import { runResearchStream, type ResearchStreamEvent } from "../services/api";

const form = reactive({ topic: "", searchApi: "" });
const loading = ref(false);
const error = ref("");// 存报错信息
const progressLogs = ref<string[]>([]);
const logsCollapsed = ref(false);
const isExpanded = ref(false);
const todoTasks = ref<TodoTaskView[]>([]);// 存放所有任务卡片的数组（数据仓库）
const activeTaskId = ref<number | null>(null);
const reportMarkdown = ref("");

const summaryHighlight = ref(false);
const sourcesHighlight = ref(false);
const reportHighlight = ref(false);
const toolHighlight = ref(false);

let currentController: AbortController | null = null;

export function useResearchState() {
  const totalTasks = computed(() => todoTasks.value.length);
  const completedTasks = computed(() =>
    todoTasks.value.filter((task) => task.status === "completed").length
  );

  const currentTask = computed(() => {
    if (activeTaskId.value !== null) {
      return todoTasks.value.find((task) => task.id === activeTaskId.value) ?? null;
    }
    return todoTasks.value[0] ?? null;
  });

  const pulse = (flag: typeof summaryHighlight) => {
    flag.value = false;
    requestAnimationFrame(() => {
      flag.value = true;
      window.setTimeout(() => { flag.value = false; }, 1200);
    });
  };

  function parseSources(raw: string): SourceItem[] {
    if (!raw) return [];

    const blocks = raw
      .split(/\n?信息来源:\s*/g)
      .map((chunk) => chunk.trim())
      .filter(Boolean);

    const fromBlocks: SourceItem[] = blocks
      .map((block) => {
        const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
        const title = lines[0] ?? "";
        const urlMatch = block.match(/URL:\s*(https?:\/\/[^\s\n]+)/i);
        const url = urlMatch?.[1] ?? "";
        const snippetMatch = block.match(/信息内容:\s*([\s\S]*?)(?:\n详细信息内容限制|$)/);
        const snippet = snippetMatch?.[1]?.trim() ?? "";

        if (!title && !url && !snippet) return null;
        return {
          title: title || url || "未命名来源",
          url,
          snippet,
          raw: block,
        };
      })
      .filter((item): item is SourceItem => Boolean(item));

    if (fromBlocks.length > 0) {
      return fromBlocks;
    }

    // 兜底：仅从文本里提取 URL。
    const urls = Array.from(new Set(raw.match(/https?:\/\/[^\s\]"')]+/g) ?? []));
    return urls.map((url) => ({
      title: url,
      url,
      snippet: "",
      raw,
    }));
  }

  function findTask(taskId: unknown): TodoTaskView | undefined {
    const numeric = typeof taskId === "number" ? taskId : typeof taskId === "string" ? Number(taskId) : NaN;
    if (Number.isNaN(numeric)) return undefined;
    return todoTasks.value.find((task) => task.id === numeric);
  }

  function applyNoteMetadata(task: TodoTaskView, payload: Record<string, unknown>): void {
    if (typeof payload.note_id === "string" && payload.note_id.trim()) task.noteId = payload.note_id.trim();
    if (typeof payload.note_path === "string" && payload.note_path.trim()) task.notePath = payload.note_path.trim();
  }

  const resetWorkflowState = () => {
    todoTasks.value = [];
    activeTaskId.value = null;
    reportMarkdown.value = "";
    progressLogs.value = [];
    summaryHighlight.value = false;
    sourcesHighlight.value = false;
    reportHighlight.value = false;
    toolHighlight.value = false;
    logsCollapsed.value = false;
  };

  const handleSubmit = async () => {
    if (!form.topic.trim()) { error.value = "请输入研究主题"; return; }
    if (currentController) { currentController.abort(); currentController = null; }
    loading.value = true;
    error.value = "";
    isExpanded.value = true;
    resetWorkflowState();

    const controller = new AbortController();
    currentController = controller;

    const payload = { topic: form.topic.trim(), search_api: form.searchApi || undefined };

    try {
      await runResearchStream(payload, (event: ResearchStreamEvent) => {
        const data = event as Record<string, unknown>;
        const eventType =
          typeof data.type === "string"
            ? data.type
            : typeof data.types === "string"
              ? data.types
              : "unknown";

        if (eventType === "status") {
          const message = typeof data.message === "string" ? data.message : "";
          if (message) progressLogs.value.push(message);
          return;
        }
        // 当后端大模型把任务规划好时，这里瞬间生成一排灰色的任务卡片。
        if (eventType === "todo_list") {
          const tasks = Array.isArray(data.tasks) ? data.tasks : [];
          todoTasks.value = tasks.map((taskLike, index) => {
            const task = (taskLike ?? {}) as Record<string, unknown>;
            const id = typeof task.id === "number" ? task.id : index + 1;
            return {
              id,
              title: typeof task.title === "string" ? task.title : `任务 ${id}`,
              intent: typeof task.intent === "string" ? task.intent : "",
              query: typeof task.query === "string" ? task.query : "",
              status: typeof task.status === "string" ? task.status : "pending",
              summary: typeof task.summary === "string" ? task.summary : "",
              sourcesSummary:
                typeof task.sources_summary === "string" ? task.sources_summary : "",
              sourceItems: [],
              notices: [],
              noteId: typeof task.note_id === "string" ? task.note_id : null,
              notePath: typeof task.note_path === "string" ? task.note_path : null,
              toolCalls: [],
            } satisfies TodoTaskView;
          });

          if (todoTasks.value.length > 0) {
            activeTaskId.value = todoTasks.value[0].id;
          }
          progressLogs.value.push(`已生成 ${todoTasks.value.length} 个研究任务`);
          return;
        }
        // 在某个子任务发生重大状态改变（如“刚开始”、“已完成”、“跳过”）时，对前端 UI 进行全方位的数据同步和焦点切换
        if (eventType === "task_status") {
          const task = findTask(data.task_id);
          if (!task) return;

          if (typeof data.status === "string") {
            task.status = data.status;
          }
          if (typeof data.summary === "string") {
            task.summary = data.summary;
            pulse(summaryHighlight);
          }
          if (typeof data.sources_summary === "string") {
            task.sourcesSummary = data.sources_summary;
            task.sourceItems = parseSources(data.sources_summary);
            pulse(sourcesHighlight);
          }

          applyNoteMetadata(task, data);
          activeTaskId.value = task.id;
          return;
        }
        // 把清洗好的 URL 和标题塞进对应任务的数组里，页面上立刻刷出参考链接列表
        if (eventType === "sources") {
          const task = findTask(data.task_id);
          if (!task) return;

          if (typeof data.latest_sources === "string") {
            task.sourcesSummary = data.latest_sources;
            task.sourceItems = parseSources(data.latest_sources);
          }

          if (task.sourceItems.length === 0 && typeof data.raw_context === "string") {
            task.sourceItems = parseSources(data.raw_context);
          }

          if (typeof data.backend === "string") {
            task.notices.push(`搜索后端：${data.backend}`);
          }

          applyNoteMetadata(task, data);
          pulse(sourcesHighlight);
          return;
        }
        // 后端大模型每吐出一个词（chunk），这里就把它加到 task.summary 的末尾。Vue 监听到变化，页面上就多出了一个字。这就是你看到的丝滑打字机效果的底层真面目。
        if (eventType === "task_summary_chunk") {
          const task = findTask(data.task_id);
          if (!task) return;

          if (typeof data.content === "string" && data.content) {
            task.summary += data.content;
            pulse(summaryHighlight);
          }
          applyNoteMetadata(task, data);
          return;
        }
        // AI Agent 的“行为透明化”（也就是常说的“白盒化追踪”）
        if (eventType === "tool_call") {
          const task = findTask(data.task_id);
          if (!task) return;

          task.toolCalls.push({
            eventId: typeof data.event_id === "number" ? data.event_id : Date.now(),
            agent: typeof data.agent === "string" ? data.agent : "unknown",
            tool: typeof data.tool === "string" ? data.tool : "unknown",
            parameters:
              typeof data.parameters === "object" && data.parameters !== null
                ? (data.parameters as Record<string, unknown>)
                : {},
            result: typeof data.result === "string" ? data.result : "",
            noteId: typeof data.note_id === "string" ? data.note_id : null,
            notePath: typeof data.note_path === "string" ? data.note_path : null,
            timestamp: Date.now(),
          });

          applyNoteMetadata(task, data);
          pulse(toolHighlight);
          return;
        }

        if (eventType === "final_report") {
          if (typeof data.report === "string") {
            reportMarkdown.value = data.report;
          }
          progressLogs.value.push("研究完成，已生成最终报告");
          pulse(reportHighlight);
          return;
        }

        if (eventType === "error") {
          const detail = typeof data.detail === "string" ? data.detail : "未知错误";
          error.value = detail;
          progressLogs.value.push(`错误：${detail}`);
          return;
        }

        if (eventType === "done") {
          progressLogs.value.push("研究流程结束");
        }
      }, { signal: controller.signal });// 带着这个新令牌去发请求
      if (!reportMarkdown.value) reportMarkdown.value = "暂无生成的报告";
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        progressLogs.value.push("已取消当前研究任务");
      } else {
        error.value = err instanceof Error ? err.message : "请求失败";
      }
    } finally {
      loading.value = false;
      if (currentController === controller) currentController = null;
    }
  };

  const cancelResearch = () => {
    if (!loading.value || !currentController) return;
    progressLogs.value.push("正在尝试取消当前研究任务…");
    currentController.abort();
  };

  const goBack = () => {
    if (loading.value) return;
    isExpanded.value = false;
  };

  const startNewResearch = () => {
    if (loading.value) cancelResearch();
    resetWorkflowState();
    isExpanded.value = false;
    form.topic = "";
    form.searchApi = "";
  };

  return {
    form, loading, error, progressLogs, logsCollapsed, isExpanded,
    todoTasks, activeTaskId, reportMarkdown, summaryHighlight, sourcesHighlight,
    reportHighlight, toolHighlight, totalTasks, completedTasks, currentTask,
    handleSubmit, cancelResearch, goBack, startNewResearch, currentController,
  };
}