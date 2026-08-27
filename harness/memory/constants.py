"""记忆与会话的常量。"""

SESSION_JSONL = "session.jsonl"
SHORT_TERM_MAX = 3
SESSION_COMPRESS_USER_TEXT = "【历史会话压缩】请将此前完整对话总结为简明摘要，便于后续继续本话题。"
SESSION_COMPRESS_MARKER = "【历史会话压缩】"
DIALOGUE_EVENT_TYPES = frozenset(
    {"user/message", "assistant/message", "tool/call", "tool/result"}
)

MEMORY_TEMPLATE = """---
name: user-memory
description: 用户分层记忆。默认仅加载「记忆种类」与「用户画像与偏好」；短期/长期请用 load_memory 按需加载。
---

# 用户记忆

本文件由 Harness 在**每次启动**时视「是否有新对话」用大模型增量更新；非工具沙箱产物。

## 记忆种类与目的

| 种类 | 层级 | 目的 | 默认注入 | 按需加载 |
|------|------|------|----------|----------|
| 短期记忆（工作记忆） | L1 | 最近约三次询问摘要 | 否 | `load_memory("short")` |
| 长期·语义记忆 | L2 | 稳定事实与概念 | 否 | `load_memory("long")` |
| 长期·情节记忆 | L2 | 过往会话/事件 | 否 | `load_memory("long")` |
| 长期·程序记忆 | L2 | 「怎么做」的习惯与步骤 | 否 | `load_memory("long")` |
| 用户画像与偏好 | L3 | 身份、沟通与编码偏好 | 是 | （已在 system） |

## 用户画像与偏好

### 画像
- （暂无）

### 偏好
- （暂无）

## 短期记忆

（最近约三次询问摘要；启动 Consolidation 时由模型更新）

## 长期记忆

### 语义记忆
- （暂无）

### 情节记忆
- （暂无）

### 程序记忆
- （暂无）
"""
