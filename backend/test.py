import json
import re
from typing import List, Any


# --- 1. 模拟依赖的外部函数和配置 ---
def strip_thinking_tokens(text: str) -> str:
    """模拟去除思考过程的标签，例如 DeepSeek 的 <think>"""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


class MockConfig:
    strip_thinking_tokens = True


class TaskExtractor:
    def __init__(self):
        self._config = MockConfig()

    def _extract_json_payload(self, text: str):
        """模拟从文本中提取 JSON（假设大模型有时会加上 markdown 代码块标记）"""
        try:
            # 简单去除 markdown 的 ```json 和 ```
            clean_text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except json.JSONDecodeError:
            return None

    def _extract_tool_payload(self, text: str):
        """模拟从工具调用的特定格式中提取参数"""
        if "[TOOL_CALL: create_tasks]" in text:
            # 假装解析出了工具的参数
            return {"tasks": [{"id": "tool_01", "name": "工具生成的任务"}]}
        return None

    # --- 这里放你的原函数 ---
    def _extract_tasks(self, raw_response: str) -> List[dict[str, Any]]:
        text = raw_response.strip()
        if self._config.strip_thinking_tokens:
            text = strip_thinking_tokens(text)

        json_payload = self._extract_json_payload(text)
        tasks: List[dict[str, Any]] = []

        # 分支 1：解析出来是字典，且里面有 "tasks" 键
        if isinstance(json_payload, dict):
            candiate = json_payload.get("tasks")
            if isinstance(candiate, list):
                for item in candiate:
                    if isinstance(item, dict):
                        tasks.append(item)

        # 分支 2：解析出来直接就是一个列表
        elif isinstance(json_payload, list):
            for item in json_payload:
                if isinstance(item, dict):
                    tasks.append(item)

        # 分支 3：前面都失败了，尝试作为工具调用(Tool Call)来解析
        if not tasks:
            tool_payload = self._extract_tool_payload(text)
            if tool_payload and isinstance(tool_payload.get("tasks"), list):
                for item in tool_payload["tasks"]:
                    if isinstance(item, dict):
                        tasks.append(item)

        return tasks


# --- 2. 开始测试 ---
if __name__ == "__main__":
    extractor = TaskExtractor()

    print("=== 测试开始 ===")

    # 场景 1：最标准的字典格式 (命中分支 1)
    response_1 = '{"tasks": [{"id": 1, "name": "洗碗"}, {"id": 2, "name": "扫地"}]}'
    print(f"场景 1 (标准 Dict): {extractor._extract_tasks(response_1)}")

    # 场景 2：大模型偷懒，直接返回了数组 (命中分支 2)
    response_2 = '[{"id": 3, "name": "买菜"}, {"id": 4, "name": "做饭"}]'
    print(f"场景 2 (直接 List): {extractor._extract_tasks(response_2)}")

    # 场景 3：带有 Markdown 代码块包裹的 JSON (考察提取器的鲁棒性)
