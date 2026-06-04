from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

# 如果安装了 python-dotenv，则从 backend/.env 加载环境变量。
# 这确保运行 `python src1/main.py` 时使用的设置与以下情况相同：
# 当项目启动时，如果环境变量已在仓库中配置。

try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    load_dotenv(_Path(__file__).parent.parent / ".env")
except Exception:
    # dotenv 缺失或 .env 文件不存在 — 忽略并继续
    pass

if __package__ in (None, ""):
    # 通过将 backend 添加到 sys.path，允许从 backend/src1 运行 `python .\main.py`。
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from src1.config import Configuration, SearchAPI
from src1.agent import DeepResearchAgent


# 添加控制台日志处理程序
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


# 添加错误日志文件处理程序
logger.add(
    sink=sys.stderr,
    level="ERROR",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)

class ResearchRequest(BaseModel):
    """“触发研究运行的有效载荷。”."""

    topic: str = Field(..., description="用户提供的研究课题")
    search_api: SearchAPI | None = Field(
        default=None,
        description="覆盖通过环境变量配置的默认搜索后端",
    )

class ResearchResponse(BaseModel):
    """“包含生成的报告和结构化任务的HTTP响应。”."""

    report_markdown: str = Field(
        ..., description="Markdown格式的研究报告，包含以下部分"
    )
    todo_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="结构化的待办事项，包含摘要和来源",
    )

def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    """“屏蔽敏感标记，同时保留首尾字符。”."""
    if not value:
        return "unset"

    if len(value) <= visible * 2:
        return "*" * len(value)

    return f"{value[:visible]}...{value[-visible:]}"

def _build_config(payload: ResearchRequest) -> Configuration:
    overrides: Dict[str, Any] = {}

    if payload.search_api is not None:
        overrides["search_api"] = payload.search_api

    return Configuration.from_env(overrides=overrides)

def create_app()-> FastAPI:
    def log_startup_configuration() -> None:
        config = Configuration.from_env()

        if config.llm_provider == "ollama":
            base_url = config.sanitized_ollama_url()
        elif config.llm_provider == "lmstudio":
            base_url = config.lmstudio_base_url
        else:
            base_url = config.llm_base_url or "unset"

        logger.info(
            "DeepResearch 配置已加载: provider={} model={} base_url={} search_api={} "
            "max_loops={} fetch_full_page={} tool_calling={} strip_thinking={} api_key={}",
            config.llm_provider,
            config.resolved_model() or "unset",
            base_url,
            (config.search_api.value if isinstance(config.search_api, SearchAPI) else config.search_api),
            config.max_web_research_loops,
            config.fetch_full_page,
            config.use_tool_calling,
            config.strip_thinking_tokens,
            _mask_secret(config.llm_api_key),
        )
    # 在 FastAPI 应用启动之前和关闭之后，集中管理并执行特定的代码逻辑
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        log_startup_configuration()
        yield

    app = FastAPI(title="auto deepsearch", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/research", response_model=ResearchResponse)
    def run_research(payload: ResearchRequest) -> ResearchResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
            result = agent.run(payload.topic)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as  e:
            raise HTTPException(status_code=500, detail=str(e))

        todo_payload = [
            {
                "id": item.id,
                "title": item.title,
                "intent": item.intent,
                "query": item.query,
                "status": item.status,
                "summary": item.summary,
                "sources_summary": item.sources_summary,
                "note_id": item.note_id,
                "note_path": item.note_path,
            }
            for item in result.todo_items
        ]
        return ResearchResponse(
            report_markdown=(result.report_markdown or result.running_summary or ""),
            todo_items=todo_payload,
        )

    @app.post("/research/stream")
    async def stream_research(payload: ResearchRequest) -> StreamingResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        async def event_iterator() -> AsyncIterator[str]:
            try:
                async for event in agent.run_stream(payload.topic):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:  # pragma: no cover - defensive guardrail
                logger.exception("Streaming research failed")
                error_payload = {"types": "error", "detail": str(exc)}
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    return app
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src1.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
