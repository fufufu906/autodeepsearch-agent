import json
import re
from typing import Dict, List, Callable


# ==========================================
# 1. 定义工具箱（模拟 ToolRegistry 和 NoteTool）
# ==========================================
class SimpleNoteTool:
    """手写本地笔记工具：真正去模拟磁盘或内存操作"""

    def __init__(self):
        # 用字典模拟本地磁盘存储
        self.disk_storage: Dict[str, str] = {}
        self.counter = 0

    def run(self, action: str, title: str = "", content: str = "", note_id: str = "") -> str:
        if action == "create":
            self.counter += 1
            new_id = f"note_2026_00{self.counter}"
            self.disk_storage[new_id] = f"【标题】: {title}\n【正文】: {content}"
            return f"成功！本地磁盘已持久化，分配的 note_id 为: {new_id}"

        elif action == "read":
            if note_id in self.disk_storage:
                return f"读取成功，文件内容如下：\n{self.disk_storage[note_id]}"
            return f"错误：本地磁盘未找到 ID 为 {note_id} 的文件。"

        return "错误：未知的操作类型"


# ==========================================
# 2. 核心：手写自动化状态机智能体
# ==========================================
class MyHandwrittenAgent:
    def __init__(self, system_prompt: str, mock_llm_backend: Callable[[List[dict]], str]):
        self.system_prompt = system_prompt
        # 传入一个模拟的大模型芯片函数
        self.llm_backend = mock_llm_backend

        # 核心：每个 Agent 实例拥有自己绝对隔离的独立对话历史历史
        self.history: List[dict] = [
            {"role": "system", "content": self.system_prompt}
        ]

        # 实例化本地工具，并注册进内部路由字典
        self.note_tool = SimpleNoteTool()
        self.tools_router = {
            "note": self.note_tool
        }

        # 正则雷达：拦截工具调用
        self.TOOL_PATTERN = re.compile(r'\[TOOL_CALL:(?P<tool_name>[a-zA-Z_]+):(?P<body>.*?)\]', re.DOTALL)

    def run(self, user_question: str) -> str:
        """外部节点调用入口，内部隐藏 while True 自动流转状态机"""
        # 1. 接收用户的原始任务，推入记忆时间线
        self.history.append({"role": "user", "content": user_question})

        print(f"\n🚀 [状态机启动] 开始处理任务: '{user_question}'")
        step = 0

        # 2. 开启状态机无限循环
        while True:
            step += 1
            print(f"\n--- 🔄 状态机内部循环第 {step} 轮 ---")
            print("[状态 A: 推理] 驱动底层大模型芯片进行单步思考...")

            # 喂入包含工具结果的完整历史，让大模型产生单步输出
            response_text = self.llm_backend(self.history)

            # 将模型的思考/输出追加到历史中
            self.history.append({"role": "assistant", "content": response_text})

            # [状态 B: 拦截] 扫描大模型的输出，检查是否包含工具调用信号
            match = self.TOOL_PATTERN.search(response_text)

            if not match:
                # 快乐路径：模型没有输出 [TOOL_CALL]，说明它认为研究结束了，吐出最终报告
                print("🎉 [状态机退出] 大模型说它做完了，输出最终结论。")
                return response_text

            # [状态 C: 接管] 拦截到了工具信号，开启本地自动化执行
            tool_name = match.group("tool_name")
            body_str = match.group("body").strip()

            print(f"🚨 [雷达拦截] 发现大模型试图申请工具: '{tool_name}'")
            print(f"📦 [提取载荷] 抓取到的原始参数字符串: {body_str}")

            # 3. 自研混合解析（这里写一个简易防御解析）
            try:
                payload = json.loads(body_str)
            except json.JSONDecodeError:
                print("⚠️ [格式损坏] 发现标准 JSON 损坏，启动降级手工切分...")
                payload = {}
                # 简单处理 action=create, title=xxx 这种格式
                parts = [p.strip() for p in body_str.split(",") if p.strip()]
                for part in parts:
                    if "=" in part:
                        k, v = part.split("=", 1)
                        payload[k.strip()] = v.strip()

            # 4. 自动动态路由并执行
            tool_instance = self.tools_router.get(tool_name)
            if tool_instance:
                print(f"⚙️ [本地执行] 路由成功，操作系统正在本地硬核跑 {tool_name} 工具...")
                # 真正调用本地 Python 代码跑磁盘
                tool_result = tool_instance.run(**payload)
            else:
                tool_result = f"错误：系统未注册名为 {tool_name} 的工具"

            print(f"📥 [执行结果] 本地代码跑完，抓取到的磁盘反馈: {tool_result}")

            # 5. 隐形记忆拼接（Feedback）
            # 把热腾腾的磁盘结果硬塞进大模型的历史里，假装是“系统通知”
            self.history.append({
                "role": "tool",
                "name": tool_name,
                "content": tool_result
            })
            print("🔗 [记忆绑牢] 已将工具结果暗中拼入 Agent 历史队列，状态机自动进入下一轮循环。")


# ==========================================
# 3. 编写一个大模型模拟芯片（模拟 OpenAI/Ollama 接口）
# ==========================================
def mock_llm_response(messages: List[dict]) -> str:
    """
    通过判断对话历史里的最后一句话，去模拟大模型的返回。
    真实场景下，这里应该用客户端把 messages 发给真实的 DeepSeek 或 OpenAI。
    """
    last_msg = messages[-1]

    # 第一步：用户刚进门，大模型决定去本地建一个草稿笔记
    if last_msg["role"] == "user":
        return "分析：为了完成用户的任务，我需要先建立一个任务笔记持久化存储。\n请系统执行：[TOOL_CALL:note:{\"action\":\"create\",\"title\":\"AI现状调研\",\"content\":\"正在搜集资料...\"}]"

    # 第二步：大模型看到本地系统拼回来的新记忆（成功拿到了 note_id），它决定去读它
    if last_msg["role"] == "tool" and "note_2026_001" in last_msg["content"]:
        return "分析：我知道笔记创建成功了，ID是 note_2026_001。现在我需要读取它确认里面的正文。\n请系统执行：[TOOL_CALL:note:action=read, note_id=note_2026_001]"

    # 第三步：大模型看到了读取出来的正文，认为任务圆满结束，给出最终研报
    if last_msg["role"] == "tool" and "读取成功" in last_msg["content"]:
        return "【最终研究报告】\n经过全网并发检索与本地笔记比对，当前大模型正全面朝端侧部署与长文本推理（Thinking Tokens）演进，报告沉淀完毕。"

    return "思考完毕，没有多余动作。"


# ==========================================
# 4. 组装并测试你的手写系统
# ==========================================
if __name__ == "__main__":
    system_instruction = "你是一个全能的研究专家，你可以通过 [TOOL_CALL:note:...] 格式读写本地笔记系统。"

    # 实例化你纯手写的 Agent
    agent = MyHandwrittenAgent(system_prompt=system_instruction, mock_llm_backend=mock_llm_response)

    # 激活并跑通这个完全属于你的状态机
    final_report = agent.run("请帮我写一份人工智能最新的发展报告。")

    print("\n==========================================")
    print("🔥 前端最终收到的报告内容：")
    print(final_report)