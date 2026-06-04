"""State models used by the deep research workflow."""

import operator
from dataclasses import dataclass, field
from typing import List, Optional

from typing_extensions import Annotated, TypedDict


def task_reducer(existing: list, updates: list) -> list:
    """按 ID 合并待办事项——将更新内容插入到现有条目中"""
    by_id: dict[int, object] = {t.id: t for t in existing}
    for update in updates:
        by_id[update.id] = update
    return list(by_id.values())


@dataclass(kw_only=True)
class TodoItem:
    """单个待办任务项。"""

    id: int
    title: str
    intent: str
    query: str
    status: str = field(default="pending")
    summary: Optional[str] = field(default=None)
    sources_summary: Optional[str] = field(default=None)
    notices: list[str] = field(default_factory=list)
    note_id: Optional[str] = field(default=None)
    note_path: Optional[str] = field(default=None)
    stream_token: Optional[str] = field(default=None)


class SummaryState(TypedDict, total=False):
    """为深度研究工作流提供与 LangGraph 兼容的状态。

带有 reducer（``operator.add`` / ``task_reducer``）注解的字段

会在并发节点返回片段时自动合并，从而

取代对 ``threading.Lock`` 的需求。
    """

    research_topic: str
    search_query: str
    web_research_results: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]
    research_loop_count: Annotated[int, operator.add]
    running_summary: str
    todo_items: Annotated[list, task_reducer]
    structured_report: Optional[str]
    report_note_id: Optional[str]
    report_note_path: Optional[str]
    # Send() 扇出注入的瞬态键 — 不属于持久状态的一部分。
    _current_task: object
    _task_step: int


@dataclass(kw_only=True)
class SummaryStateInput:
    research_topic: str = field(default=None)  # Report topic


@dataclass(kw_only=True)
class SummaryStateOutput:
    running_summary: str = field(default=None)  # Backward-compatible文本
    report_markdown: Optional[str] = field(default=None)
    todo_items: List[TodoItem] = field(default_factory=list)
