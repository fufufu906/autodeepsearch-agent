
from __future__ import annotations

import re


def strip_tool_calls(text: str)-> str:
    if not text:
        return  text

    pattern = re.compile(r"\[TOOL_CALL:[^\]]+\]")
    return  pattern.sub("",text)