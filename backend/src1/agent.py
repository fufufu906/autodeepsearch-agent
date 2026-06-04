"""DeepResearchAgent — LangGraph-based research orchestration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, cast

from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent, ToolRegistry
from hello_agents.tools import NoteTool
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.config import get_stream_writer
from langgraph.types import Send

from src1.config import Configuration
from src1.models import SummaryState, SummaryStateOutput, TodoItem
from src1.prompts import (
    report_writer_instructions,
    task_summarizer_instructions,
    todo_planner_instructions,
)
from src1.service.planner import PlanningService
from src1.service.reporter import ReportingService
from src1.service.search import dispatch_search, prepare_research_context
from src1.service.summarizer import SummarizationService
from src1.service.tool_events import ToolCallTracker

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
except ModuleNotFoundError:
    from src1.tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

network_retry_policy = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
)

logger = logging.getLogger(__name__)


# ── state proxy ──────────────────────────────────────────────────────────────
class _StateProxy:
    """为了与服务层兼容，提供状态字典的属性访问视图。
现有服务（Planner、Summarizer、Reporter）需要 ``state.field`` 属性访问。
此代理将 LangGraph 的 ``TypedDict`` 状态桥接到该接口，无需复制
    """

    _data: dict[str, Any]
    #不用复制任何内存、不破坏 LangGraph 的底层字典结构，让原本只支持方括号的字典，瞬间支持“点号”读写。
    def __init__(self, data: dict[str, Any]) -> None:
        object.__setattr__(self, "_data", data)#防止“无限递归死循环（Infinite Recursion）”导致程序硬崩溃

    def __getattr__(self, name: str) -> Any:
        if name == "_data":
            raise AttributeError(name)
        return self._data.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("_data",):
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value


def _make_initial_state(topic: str) -> SummaryState:
    return {
        "research_topic": topic,
        "search_query": "",
        "web_research_results": [],
        "sources_gathered": [],
        "research_loop_count": 0,
        "running_summary": "",
        "todo_items": [],
        "structured_report": None,
        "report_note_id": None,
        "report_note_path": None,
    }


# ── agent ────────────────────────────────────────────────────────────────────
class DeepResearchAgent:
    def __init__(self, config: Configuration | None = None) -> None:
        self.config = config or Configuration.from_env()
        self.llm = self._init_llm()
        self.note_tool = (
            NoteTool(workspace=self.config.notes_workspace)
            if self.config.enable_notes
            else None
        )
        self.tools_registry: ToolRegistry | None = None
        if self.note_tool:
            registry = ToolRegistry()
            registry.register_tool(self.note_tool)
            self.tools_registry = registry
        self._tool_tracker = ToolCallTracker(
            self.config.notes_workspace if self.config.enable_notes else None
        )

        self.todo_agent = self._create_tool_aware_agent(
            name="研究规划专家",
            system_prompt=todo_planner_instructions.strip(),
        )
        self.report_agent = self._create_tool_aware_agent(
            name="报告撰写专家",
            system_prompt=report_writer_instructions.strip(),
        )

        self._summarizer_factory: Callable[[], ToolAwareSimpleAgent] = (
            lambda: self._create_tool_aware_agent(
                name="任务总结专家",
                system_prompt=task_summarizer_instructions.strip(),
            )
        )

        self.Planner = PlanningService(self.todo_agent, self.config)
        self.summarizer = SummarizationService(self._summarizer_factory, self.config)
        self.reporting = ReportingService(self.report_agent, self.config)
        self._last_search_notices: list[str] = []

    # ── llm helpers (unchanged) ───────────────────────────────────────────
    def _init_llm(self) -> HelloAgentsLLM:
        llm_kwargs: dict[str, Any] = {"temperature": 0.0}
        model_id = self.config.llm_model_id or self.config.local_llm
        if model_id:
            llm_kwargs["model"] = model_id
        provider = (self.config.llm_provider or "").strip()
        if provider == "ollama":
            llm_kwargs["base_url"] = self.config.sanitized_ollama_url()
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key
            else:
                llm_kwargs["api_key"] = "ollama"
        elif provider == "lmstudio":
            llm_kwargs["base_url"] = self.config.lmstudio_base_url
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key
        else:
            if self.config.llm_base_url:
                llm_kwargs["base_url"] = self.config.llm_base_url
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key
        return HelloAgentsLLM(**llm_kwargs)

    #将一个普通的“纯文本聊天大模型（LLM）”包装成一个“具备人设（System Prompt）、具备工具箱（Tool Registry）且具备行为监控（Listener）”的真正智能体（Agent）。
    def _create_tool_aware_agent(
        self, *, name: str, system_prompt: str
    ) -> ToolAwareSimpleAgent:
        return ToolAwareSimpleAgent(
            name=name,
            llm=self.llm,
            system_prompt=system_prompt,
            enable_tool_calling=self.tools_registry is not None,
            tool_registry=self.tools_registry,
            # 【核心挂载点】：将 Tracker 的 record 方法作为探针（Listener）注入到底层
            tool_call_listener=self._tool_tracker.record,
        )

    # ── tool event helpers ────────────────────────────────────────────────
    def _drain_tool_events(
        self, state: SummaryState, *, step: int | None = None
    ) -> list[dict[str, Any]]:
        return self._tool_tracker.drain(cast(Any, _StateProxy(state)), step=step)  # type: ignore

    @staticmethod
    def _serialize_task(task: TodoItem) -> dict[str, Any]:
        return {
            "id": task.id,
            "title": task.title,
            "intent": task.intent,
            "query": task.query,
            "status": task.status,
            "summary": task.summary,
            "sources_summary": task.sources_summary,
            "note_id": task.note_id,
            "note_path": task.note_path,
            "stream_token": task.stream_token,
        }

    # ── note persistence (unchanged) ──────────────────────────────────────
    def _persist_final_report(
        self, state: SummaryState, report: str
    ) -> dict[str, Any] | None:
        if not self.note_tool or not report or not report.strip():
            return None
        note_title = f"研究报告：{state.get('research_topic', '')}".strip() or "研究报告"
        tags = ["deep_research", "report"]
        content = report.strip()
        note_id = self._find_existing_report_note_id(state)
        response = ""
        if note_id:
            response = self.note_tool.run(
                {
                    "action": "update",
                    "note_id": note_id,
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            if response.startswith("❌"):
                note_id = None
        if not note_id:
            response = self.note_tool.run(
                {
                    "action": "create",
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            note_id = self._extract_note_id_from_text(response)
        if not note_id:
            return None
        state["report_note_id"] = note_id
        if self.config.notes_workspace:
            state["report_note_path"] = str(
                Path(self.config.notes_workspace) / f"{note_id}.md"
            )
        payload: dict[str, Any] = {
            "types": "report_note",
            "note_id": note_id,
            "title": note_title,
            "content": content,
        }
        note_path = state.get("report_note_path")
        if note_path:
            payload["note_path"] = note_path
        return payload

    #利用一切线索，去追溯和拦截之前可能已经诞生过的研报 note_id。
    # 如果找到了，就意味着不需要创建新文件，直接进行覆盖更新（Update），
    # 从而完美避免了在用户磁盘中产生一堆重复的“套娃”垃圾报告文件。
    def _find_existing_report_note_id(self, state: SummaryState) -> str | None:
        if state.get("report_note_id"):
            return state["report_note_id"]
        for event in reversed(self._tool_tracker.as_dicts()):
            if event.get("tool") != "note":
                continue
            parameters = event.get("parsed_parameters") or {}
            if not isinstance(parameters, dict):
                continue
            action = parameters.get("action")
            if action not in {"create", "update"}:
                continue
            note_type = parameters.get("note_type")
            if note_type != "conclusion":
                title = parameters.get("title")
                if not (isinstance(title, str) and title.startswith("研究报告")):
                    continue
            note_id = parameters.get("note_id")
            if not note_id:
                note_id = self._tool_tracker._extract_note_id(event.get("result", ""))
            if note_id:
                return note_id
        return None

    def _extract_note_id_from_text(self, response: str) -> str | None:
        return self._tool_tracker._extract_note_id(response)

    # ── public API ────────────────────────────────────────────────────────
    def run(self, topic: str) -> SummaryStateOutput:
        graph = self._build_graph()
        initial: SummaryState = _make_initial_state(topic)
        final = graph.invoke(initial)  # type: ignore
        return SummaryStateOutput(
            running_summary=final.get("running_summary") or "",
            report_markdown=final.get("structured_report"),
            todo_items=final.get("todo_items", []),
        )

    async def run_stream(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        graph = self._build_graph()
        initial: SummaryState = _make_initial_state(topic)
        yield {"types": "status", "message": "初始化研究流程"}
        async for mode, chunk in graph.astream(initial, stream_mode=["custom"]):  # type: ignore
            if mode == "custom":
                inner = chunk.get("sse")
                if inner is not None:
                    yield inner

    # ── graph construction ────────────────────────────────────────────────
    def _build_graph(self) -> Any:  # type: ignore
        builder = StateGraph(cast(Any, SummaryState))  # type: ignore

        builder.add_node("planner", self._planner_node)  # type: ignore
        builder.add_node("search_and_summarize", self._search_and_summarize_node)  # type: ignore
        builder.add_node("reporter", self._reporter_node)  # type: ignore

        builder.add_edge(START, "planner")
        builder.add_conditional_edges(
            "planner", self._continue_to_search, ["search_and_summarize"]
        )
        builder.add_edge("search_and_summarize", "reporter")
        builder.add_edge("reporter", END)

        return builder.compile()

    # ── node: planner ─────────────────────────────────────────────────────
    #利用大模型的规划能力（Planner），
    # 把用户输入的研究课题，拆解为一组并发子任务链（todo_items），
    # 并通过异步 SSE 流（writer）将这一大局规划卡片一秒推向前端
    async def _planner_node(self, state: SummaryState) -> dict[str, Any]:
        writer = get_stream_writer()
        s = cast(Any, _StateProxy(state))  # type: ignore

        todo_items = await asyncio.to_thread(self.Planner.plan_todo_list, s)
        self._drain_tool_events(state, step=0)

        if not todo_items:
            todo_items = [await asyncio.to_thread(self.Planner.create_fallback_task, s)]

        for index, task in enumerate(todo_items, start=1):
            task.stream_token = f"task_{task.id}"
            task.status = "pending"

        writer({"sse": {
            "types": "todo_list",
            "tasks": [self._serialize_task(t) for t in todo_items],
            "step": 0,
        }})

        return {"todo_items": todo_items}

    # ── conditional edge: fan-out via Send ────────────────────────────────
    #清点前一步规划专家生产出的所有子任务链，
    # 利用 LangGraph 独有的 Send 机制，
    # 同时并发（Map 阶段）发射给下游的网页搜索与总结节点
    def _continue_to_search(self, state: SummaryState) -> list[Send]:
        tasks: list[TodoItem] = state.get("todo_items", [])
        if not tasks:
            fallback = self.Planner.create_fallback_task(cast(Any, _StateProxy(state)))  # type: ignore
            fallback.stream_token = "task_fallback"
            fallback.status = "pending"
            return [Send("search_and_summarize", {
                "_current_task": fallback,
                "_task_step": 0,
            })]
        return [
            Send("search_and_summarize", {
                "_current_task": task,
                "_task_step": index,
            })
            for index, task in enumerate(tasks, start=1)
        ]

    # ── node: search & summarize (runs concurrently via Send) ─────────────
    #报告进度 -> 并发搜索 -> 异常熔断 -> 组装上下文 -> 跨线程流式大模型摘要 -> 状态落盘。
    async def _search_and_summarize_node(
        self, state: SummaryState
    ) -> dict[str, Any]:
        writer = get_stream_writer()#SSE（Server-Sent Events）流式对讲机
        task: TodoItem = cast(TodoItem, state["_current_task"])
        step = state.get("_task_step", task.id)
        stoken = task.stream_token or ""

        try:
            # ---  task_status: in_progress ---
            task.status = "in_progress"
            writer({"sse": {
                "types": "task_status",
                "task_id": task.id,
                "status": "in_progress",
                "title": task.title,
                "intent": task.intent,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "step": step,
                "stream_token": stoken,
            }})

            # --- search (blocking → thread) ---
            @network_retry_policy
            def _safe_search():
                return dispatch_search(
                    task.query, self.config, state.get("research_loop_count", 0)
                )

            try:
                search_result, notices, answer_text, backend = (
                    await asyncio.to_thread(_safe_search)
                )
            except Exception as exc:
                logger.error("Task %d search failed after retries: %s", task.id, exc)
                search_result, notices, answer_text, backend = (
                    None, [f"搜索接口异常: {exc}"], "", "unknown"
                )

            task.notices = notices
            self._last_search_notices = notices

            for ev in self._drain_tool_events(state, step=step):
                ev.setdefault("stream_token", stoken)
                writer({"sse": ev})

            for notice in notices:
                if notice:
                    writer({"sse": {
                        "types": "status",
                        "message": notice,
                        "task_id": task.id,
                        "step": step,
                        "stream_token": stoken,
                    }})

            # --- empty-result guard ---
            #以直接将状态标为 skipped（已跳过），并提前 return 退出当前节点。
            if not search_result or not search_result.get("results"):
                task.status = "skipped"
                for ev in self._drain_tool_events(state, step=step):
                    ev.setdefault("stream_token", stoken)
                    writer({"sse": ev})
                writer({"sse": {
                    "types": "task_status",
                    "task_id": task.id,
                    "status": "skipped",
                    "title": task.title,
                    "intent": task.intent,
                    "note_id": task.note_id,
                    "note_path": task.note_path,
                    "step": step,
                    "stream_token": stoken,
                }})
                return {"todo_items": [task]}


            # --- prepare context ---
            sources_summary, context = prepare_research_context(
                search_result, answer_text, self.config
            )
            task.sources_summary = sources_summary

            for ev in self._drain_tool_events(state, step=step):
                ev.setdefault("stream_token", stoken)
                writer({"sse": ev})

            writer({"sse": {
                "types": "sources",
                "task_id": task.id,
                "latest_sources": sources_summary,
                "raw_context": context,
                "step": step,
                "backend": backend,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "stream_token": stoken,
            }})

            # --- streaming LLM summary ---
            # 在单个工作线程中创建和使用 HTTP 流
            # 以避免跨线程生成器消费。
            summary_text: str
            chunk_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
            loop = asyncio.get_running_loop()#跨线程

            #纯后台线程中运行，负责拉取 LLM 响应流
            def _run_llm_stream() -> None:
                try:
                    stream, getter = _make_stream()
                    for chunk in stream:
                        if chunk:
                            loop.call_soon_threadsafe(
                                chunk_queue.put_nowait, ("chunk", chunk)
                            )
                    loop.call_soon_threadsafe(
                        chunk_queue.put_nowait, ("done", getter())
                    )
                except Exception as exc:
                    loop.call_soon_threadsafe(
                        chunk_queue.put_nowait, ("error", exc)
                    )

            @network_retry_policy
            def _make_stream():
                return self.summarizer.stream_task_summary(
                    cast(Any, _StateProxy(state)), task, context  # type: ignore
                )

            loop.run_in_executor(None, _run_llm_stream)  # type: ignore

            summary_text = ""
            while True:
                kind, payload = await chunk_queue.get()
                if kind == "chunk":
                    writer({"sse": {
                        "types": "task_summary_chunk",
                        "task_id": task.id,
                        "content": payload,
                        "step": step,
                        "note_id": task.note_id,
                        "stream_token": stoken,
                    }})
                elif kind == "done":
                    summary_text = payload
                    break
                elif kind == "error":
                    logger.error(
                        "Task %d LLM stream worker failed: %s", task.id, payload
                    )
                    writer({"sse": {
                        "types": "task_summary_chunk",
                        "task_id": task.id,
                        "content": f"\n\n[AI 生成摘要时发生错误: {payload}]",
                        "step": step,
                        "note_id": task.note_id,
                        "stream_token": stoken,
                    }})
                    summary_text = f"生成失败: {payload}"
                    break

            task.summary = summary_text.strip() if summary_text else "暂无可用信息"
            task.status = "completed"

            for ev in self._drain_tool_events(state, step=step):
                ev.setdefault("stream_token", stoken)
                writer({"sse": ev})

            writer({"sse": {
                "types": "task_status",
                "task_id": task.id,
                "status": "completed",
                "summary": task.summary,
                "sources_summary": task.sources_summary,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "step": step,
                "stream_token": stoken,
            }})

            return {
                "web_research_results": [context],
                "sources_gathered": [sources_summary],
                "research_loop_count": 1,
                "todo_items": [task],
            }

        except Exception as exc:
            logger.exception("Task %d unexpected error: %s", task.id, exc)
            task.status = "error"
            writer({"sse": {
                "types": "task_status",
                "task_id": task.id,
                "status": "error",
                "title": task.title,
                "intent": task.intent,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "step": step,
                "stream_token": stoken,
                "error_message": str(exc),
            }})
            return {"todo_items": [task]}

    # ── node: reporter ────────────────────────────────────────────────────
    async def _reporter_node(self, state: SummaryState) -> dict[str, Any]:
        writer = get_stream_writer()
        s = cast(Any, _StateProxy(state))  # type: ignore

        report = await asyncio.to_thread(self.reporting.generate_report, s)
        final_step = len(state.get("todo_items", [])) + 1

        for ev in self._drain_tool_events(state, step=final_step):
            writer({"sse": ev})

        note_event = self._persist_final_report(state, report)
        if note_event:
            writer({"sse": note_event})

        writer({"sse": {
            "types": "final_report",
            "report": report,
            "note_id": state.get("report_note_id"),
            "note_path": state.get("report_note_path"),
        }})
        writer({"sse": {"types": "done"}})

        return {"structured_report": report, "running_summary": report}
