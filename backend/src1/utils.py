
from __future__ import annotations

import logging
from typing import Any, Dict, List, Union

CHARS_PER_TOKEN = 4

logger = logging.getLogger(__name__)

def get_config_value(value :Any) ->str:
    return  value if isinstance(value, str) else value.value

def strip_thinking_tokens(text: str) -> str:
    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>") + len("</think>")
        text = text[:start] + text[end:]
    return text
# 去重（Deduplicate）：通过网址（URL）作为唯一键，把搜索引擎返回的重复网页刷掉。
# 转换为结构化字符串（Format to Str）：把清洗后的列表，拼装成带有特定暗号标签的、规范的 Markdown 长文本字符串。
def deduplicate_and_format_sources(
    search_response: Dict[str, Any] | List[Dict[str, Any]],
    max_tokens_per_source: int,
    *,
    fetch_full_page: bool = False,
) -> str:
    if isinstance(search_response, dict):
        sources_list = search_response.get("results", [])
    else:
        sources_list = search_response

    unique_sources: dict[str, Dict[str, Any]] = {}
    for source in sources_list:
        url = source.get("url")
        if not url:
            continue# 没有网址的垃圾数据直接过滤掉
        if url not in unique_sources:# 核心：只有当这个 URL 第一次出现时，才把它存进字
            unique_sources[url] = source

    formatted_parts: List[str] = []
    for source in unique_sources.values():
        title = source.get("title") or source.get("url", "")
        content = source.get("content", "")
        formatted_parts.append(f"信息来源: {title}\n\n")
        formatted_parts.append(f"URL: {source.get('url', '')}\n\n")
        formatted_parts.append(f"信息内容: {content}\n\n")
        # 长文本防溢出截断
        if fetch_full_page:
            raw_content = source.get("raw_content")
            if raw_content is None:
                logger.debug("raw_content missing for %s", source.get("url", ""))
                raw_content = ""
            char_limit = max_tokens_per_source * CHARS_PER_TOKEN
            if len(raw_content) > char_limit:
                raw_content = f"{raw_content[:char_limit]}... [truncated]"
            formatted_parts.append(
                f"详细信息内容限制为 {max_tokens_per_source} 个 token: {raw_content}\n\n"
            )

    return "".join(formatted_parts).strip()

# 包含搜索结果的 Python 字典（Dict）转换并提炼为一个结构化的 Markdown 列表字符串（str）
def format_sources(search_results: Dict[str, Any] | None) -> str:

    if not search_results:
        return ""

    results = search_results.get("results", [])
    return "\n".join(
        f"* {item.get('title', item.get('url', ''))} : {item.get('url', '')}"
        for item in results
        if item.get("url")
    )
