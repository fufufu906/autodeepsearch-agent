import json
import logging
import re
from typing import List, Any, Optional

from hello_agents import ToolAwareSimpleAgent

from src1.config import Configuration
from src1.models import TodoItem
from src1.prompts import todo_planner_instructions, get_current_date
from src1.utils import strip_thinking_tokens

logger = logging.getLogger(__name__)



TOOL_CALL_PATTERN = re.compile(
    r"\[TOOL_CALL:(?P<tool>[^:]+):(?P<body>[^\]]+)\]",
    re.IGNORECASE
)


class PlanningService:
    def __init__(self, planner_agent: ToolAwareSimpleAgent, config: Configuration) -> None:
        self._agent = planner_agent
        self._config = config

    def plan_todo_list(self, state: Any) -> List[TodoItem]:

        prompt = todo_planner_instructions.format(
            current_date= get_current_date(),
            research_topic = state.research_topic
        )

        response = self._agent.run(prompt)
        self._agent.clear_history()

        logger.info("规划器原始输出（已截断）：%s", response[:500])

        tasks_payload = self._extract_tasks(response)
        todo_items: List[TodoItem] = []

        for idx,item in enumerate(tasks_payload,start=1):
            title = str(item.get("title") or f"任务{idx}").strip()
            intent = str(item.get("intent") or "聚焦主题的关键问题").strip()
            query = str(item.get("query") or state.research_topic).strip()

            if not query:
                query = state.research_topic

            task = TodoItem(
                id=idx,
                title=title,
                intent=intent,
                query=query
            )
            todo_items.append(task)

        state.todo_items = todo_items

        titles = [task.title for task in todo_items]
        logger.info("Planned TODO items: %s", titles)
        return  todo_items

    @staticmethod
    def create_fallback_task(state: Any) -> TodoItem:

        return TodoItem(
            id=1,
            title="基础背景梳理",
            intent="收集主题的核心背景与最新动态",
            query=f"{state.research_topic} 最新进展" if state.research_topic else "基础背景梳理",
        )


    # 把大模型返回的、不可控的纯文本字符串（raw_response），强行过滤并清洗成一个格式非常严格的 List[dict[str, Any]]（字典列表）
    def _extract_tasks(self,raw_response):
        text = raw_response.strip()
        if self._config.strip_thinking_tokens:
            text = strip_thinking_tokens(text)

        json_payload = self._extract_json_payload(text)
        tasks: List[dict[str, Any]] = []

        if isinstance(json_payload,dict):
            candiate = json_payload.get("tasks")
            if isinstance(candiate,list):
                for item in candiate:
                    if isinstance(item,dict):
                        tasks.append(item)
        elif isinstance(json_payload,list):
            for item in json_payload:
                if isinstance(item,dict):
                    tasks.append(item)

        if not  tasks:
            tool_payload = self._extract_tool_payload(text)
            if tool_payload and isinstance(tool_payload.get("tasks"), list):
                for item in tool_payload["tasks"]:
                    if isinstance(item, dict):
                        tasks.append(item)

        return tasks

    # 把中间那段参数字符串安全、准确地挖出来，并把它翻译成 Python 能够直接使用的字典（dict）格式
    def _extract_tool_payload(self, text: str) -> Optional[dict[str, Any]]:

        match = TOOL_CALL_PATTERN.search(text)
        if not match:
            return None

        body = match.group("body")

        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool payload as JSON: %s", body)


        parts = [segment.strip() for segment in body.split(",") if segment.strip()]
        payload: dict[str,Any] = {}

        for part in parts:
            if "=" not in part:
                continue
            key,value = part.split("=",1)
            payload[key.strip()] = value.strip()

        return payload or None

    def _extract_json_payload(self, text: str) -> Optional[dict[str, Any] | list]:
        """尝试从文本中查找并解析 JSON 对象或数组"""

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return None

        return None


