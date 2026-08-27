"""load_memory：按需加载 MEMORY.md 中的短期/长期等层（默认 prompt 只含种类+画像）。"""

from __future__ import annotations

from langchain_core.tools import tool

from harness.memory import load_memory_layer


@tool("load_memory")
def load_memory(layer: str = "long") -> str:
    """按需加载用户记忆层。默认 system 已含「记忆种类」与「用户画像与偏好」。

    layer 可选：
    - short：短期记忆（本进程工作记忆 + MEMORY.md 短期段）
    - long：长期记忆（语义 / 情节 / 程序）
    - profile：用户画像与偏好（已在 system，一般无需再调）
    - kinds：记忆种类表
    - all：整份 MEMORY.md
    - core：与默认注入相同（种类+画像）
    """
    print(f"\033[33m→ load_memory({layer!r})\033[0m")
    return load_memory_layer(layer)
