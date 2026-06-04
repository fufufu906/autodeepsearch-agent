import json
from typing import Any

from hello_agents import ToolAwareSimpleAgent


from src1.config import Configuration
from src1.utils import strip_thinking_tokens



class ReportingService:

    def __init__(self,report_agent: ToolAwareSimpleAgent,
                 config: Configuration
                 )->None:
        self._agent = report_agent
        self._config = config
    #集并整理前面所有并发子任务的搜索结果和笔记索引，
    # 打包成一份高信息密度的终极提示词（Prompt）喂给“报告撰写专家”，
    # 指挥它去阅读所有落盘的笔记，融会贯通后撰写出最终的深度研究报告。
    def generate_report(self, state: Any) -> str:
        tasks_block = []
        for task in state.todo_items:
            summary_block = task.summary or "暂无可用信息"
            sources_block = task.sources_summary or "暂无来源"
            tasks_block.append(
                f"### 任务 {task.id}: {task.title}\n"
                f"- 任务目标：{task.intent}\n"
                f"- 检索查询：{task.query}\n"
                f"- 执行状态：{task.status}\n"
                f"- 任务总结：\n{summary_block}\n"
                f"- 来源概览：\n{sources_block}\n"
            )

        note_references = []
        for task in state.todo_items:
            if task.note_id:
                note_references.append(
                    f"- 任务 {task.id}《{task.title}》：note_id={task.note_id}"
                )
        notes_section = "\n".join(note_references) if note_references else "- 暂无可用任务笔记"
        read_template = json.dumps({"action": "read", "note_id": "<note_id>"}, ensure_ascii=False)
        create_conclusion_template = json.dumps(
            {
                "action": "create",
                "title": f"研究报告：{state.research_topic}",
                "note_type": "conclusion",
                "tags": ["deep_research", "report"],
                "content": "请在此沉淀最终报告要点",
            },
            ensure_ascii=False,
        )

        prompt = (
            f"研究主题：{state.research_topic}\n"
            f"任务概览：\n{''.join(tasks_block)}\n"
            f"可用任务笔记：\n{notes_section}\n"
            f"请针对每条任务笔记使用格式：[TOOL_CALL:note:{read_template}] 读取内容，整合所有信息后撰写报告。\n"
            f"如需输出汇总结论，可追加调用：[TOOL_CALL:note:{create_conclusion_template}] 保存报告要点。"
        )
        response = self._agent.run(prompt)
        self._agent.clear_history()
        report_text =response.strip()
        if self._config.strip_thinking_tokens:
           report_text =strip_thinking_tokens(report_text)
        return report_text or "暂无可用报告内容"

