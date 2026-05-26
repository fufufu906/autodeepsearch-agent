
import { fetchEventSource } from '@microsoft/fetch-event-source';
const baseURL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export interface ResearchRequest {
  topic: string;
  search_api?: string;
}

export interface ResearchStreamEvent {
  type?: string;
  types?: string;
  [key: string]: unknown;
}

export interface StreamOptions {
  signal?: AbortSignal;
}
export async function runResearchStream(
  payload: ResearchRequest,
  onEvent: (event: ResearchStreamEvent) => void,
  options: StreamOptions = {}
): Promise<void> {

  return new Promise((resolve, reject) => {
    fetchEventSource(`${baseURL}/research/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream"
      },
      body: JSON.stringify(payload),
      signal: options.signal,

      // 1. 处理连接打开时的鉴权或错误
      async onopen(response) {
        if (!response.ok) {
          const errorText = await response.text().catch(() => "");
          throw new Error(errorText || `研究请求失败，状态码：${response.status}`);
        }
      },

      // 2. 完美处理每个数据包（底层已经帮你处理了黏包和 UTF-8 截断问题）
      // 当且仅当它在底层完整地凑齐了一个以 \n\n 结尾的事件包后，它才会触发一次 onmessage 回调
      onmessage(msg) {
        // SSE 协议中，消息内容在 msg.data 里
        if (!msg.data) return;

        try {
          const event = JSON.parse(msg.data) as ResearchStreamEvent;

          // 兼容性处理
          if (!event.type && typeof event.types === "string") {
            event.type = event.types;
          }

          onEvent(event);

          if (event.type === "error" || event.type === "done") {
            resolve(); // 正常结束
          }
        } catch (error) {
          console.error("解析流式事件失败：", error, msg.data);
        }
      },

      // 3. 处理网络中断与重试策略
      onerror(err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // 用户主动取消，不重试
          resolve();
          throw err; // 抛出让库停止重试
        }
        // 如果是其他网络错误，你可以 return 一个数字（毫秒），它会自动重连
        // 这里为了保持你原有的逻辑，我们直接抛出错误中断
        reject(err);
        throw err;
      },

      // 连接正常断开
      onclose() {
        resolve();
      }
    }).catch((err) => {
      // 捕获顶层错误
      if (err instanceof DOMException && err.name === "AbortError") {
         return; // 忽略主动取消的报错
      }
      reject(err);
    });
  });
}