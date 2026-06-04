import logging
from typing import Tuple, Any, Optional

from hello_agents import SearchTool

from src1.config import Configuration
from src1.utils import get_config_value, format_sources, deduplicate_and_format_sources

logger = logging.getLogger(__name__)
MAX_TOKENS_PER_SOURCE = 2000
_GLOBAL_SEARCH_TOOL = SearchTool(backend="hybrid")


def _is_empty_search_error(exc: Exception) -> bool:
    """将搜索结果为空的失败情况视为非致命性错误，以便可以跳过相关任务."""
    text = str(exc).lower()
    return "no results found" in text

#全网混合检索的统一网关（Search Gateway）”角色
def dispatch_search(
    query: str,
    config: Configuration,
    loop_count: int,
) -> Tuple[dict[str, Any] | None, list[str], Optional[str], str]:
    search_api = get_config_value(config.search_api)

    try:
        raw_response = _GLOBAL_SEARCH_TOOL.run(
            {
                "input": query,
                "backend": search_api,
                "mode": "structured",
                "fetch_full_page": config.fetch_full_page,
                "max_results": 5,
                "max_tokens_per_source": MAX_TOKENS_PER_SOURCE,
                "loop_count": loop_count,
            }

        )
    except Exception as e:
        if _is_empty_search_error(e):
            notice = f"{search_api} 搜索未返回结果，将跳过该任务。"
            logger.info("Search returned no results: backend=%s query=%s", search_api, query)
            empty_payload: dict[str, Any] = {
                "results": [],
                "backend": search_api,
                "answer": None,
                "notices": [notice],
            }
            return empty_payload, [notice], None, search_api

        logger.exception("搜索工具失败：%s", e)
        raise

    if isinstance(raw_response, str):
        notices = [raw_response]
        logger.warning("搜索后端 %s 返回文本通知：%s", search_api, raw_response)
        payload: dict[str, Any] = {
            "results": [],
            "backend": search_api,
            "answer": None,
            "notices": notices,
        }
    else:
        payload =raw_response
        notices = list(payload.get("notice") or [])

    backend_label = str(payload.get("backend") or search_api)
    answer_text = payload.get("answer")
    results = payload.get("results", [])

    if notices:
        for notice in notices:
            logger.info("Search notice (%s): %s", backend_label, notice)


    logger.info(
        "Search backend=%s resolved_backend=%s answer=%s results=%s",
        search_api,
        backend_label,
        bool(answer_text),
        len(results),
    )

    return payload, notices, answer_text, backend_label

def prepare_research_context(
        search_result: dict[str, Any] | None,
        answer_text: Optional[str],
        config: Configuration,
)-> Tuple[str,str]:
    sources_summary = format_sources(search_result)
    context = deduplicate_and_format_sources(
        search_result or {"results": []},
        max_tokens_per_source=MAX_TOKENS_PER_SOURCE,
        fetch_full_page=config.fetch_full_page,
    )

    if answer_text:
        context = f"AI直接答案：\n{answer_text}\n\n{context}"

    return sources_summary, context
