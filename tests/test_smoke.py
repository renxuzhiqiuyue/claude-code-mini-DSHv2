"""冒烟测试：包结构、压缩规则、session JSON。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def test_import_packages():
    from agents.agent import build_agent
    from agents.middleware import MIDDLEWARE_STACK
    from harness.config import ROOT, MEMORY_DIR, SKILLS_DIR
    from tools import TOOLS

    assert (ROOT / "harness").is_dir()
    assert MEMORY_DIR.name == ".memory"
    assert SKILLS_DIR.name == "skills"
    assert len(MIDDLEWARE_STACK) >= 5
    assert len(TOOLS) >= 4
    assert callable(build_agent)


def test_compact_under_limit_noop():
    from harness.compaction import compact_by_char_limit, estimate_size

    msgs = [
        HumanMessage(content="hi"),
        AIMessage(content="hello"),
    ]
    out = compact_by_char_limit(msgs, limit=200_000)
    assert out is msgs or out == msgs
    assert estimate_size(msgs) < 200_000


def test_compact_over_limit_keeps_humans_and_recent_ai():
    from harness.compaction import compact_by_char_limit

    humans = [HumanMessage(content=f"user-{i}") for i in range(3)]
    old_ais = [AIMessage(content=("OLD" * 5000) + f"-{i}") for i in range(4)]
    recent = [
        AIMessage(content="recent-1"),
        ToolMessage(content="tool-out", tool_call_id="t1", name="bash"),
        AIMessage(content="recent-2"),
        AIMessage(content="recent-3"),
    ]
    msgs = humans + old_ais + recent

    fake = MagicMock()
    fake.invoke.return_value = MagicMock(content="这是较早回复的摘要")

    with patch("agents.llm.make_llm", return_value=fake):
        out = compact_by_char_limit(msgs, limit=1000)

    # 全部用户输入
    human_texts = [m.content for m in out if isinstance(m, HumanMessage) and not str(m.content).startswith("<")]
    assert human_texts == ["user-0", "user-1", "user-2"]
    # 摘要存在
    assert any(
        isinstance(m, HumanMessage) and "<ai-history-summary>" in str(m.content) for m in out
    )
    # 最近 AI 全量在尾部
    assert any(isinstance(m, AIMessage) and m.content == "recent-3" for m in out)
    assert fake.invoke.called


def test_session_json_sync(tmp_path: Path | None = None):
    from harness import memory as mem

    tmp = Path("/tmp/mini_cc_session_test")
    tmp.mkdir(exist_ok=True)
    for p in tmp.glob("session_*.json"):
        p.unlink()

    old_dir, old_file, old_state = mem.MEMORY_DIR, mem.MEMORY_FILE, mem.STATE_FILE
    mem.MEMORY_DIR = tmp
    mem.MEMORY_FILE = tmp / "MEMORY.md"
    mem.STATE_FILE = tmp / ".consolidate_state.json"
    mem._current_session = None

    mem.start_session("test")
    assert mem._current_session.suffix == ".json"

    mem.sync_session_messages(
        [
            HumanMessage(content="你好"),
            AIMessage(content="你好！"),
            ToolMessage(content="ok", tool_call_id="1", name="bash"),
        ],
        reason="test",
    )
    doc = mem._load_session_doc(mem._current_session)
    keys = [next(iter(x)) for x in doc["messages"]]
    assert keys == ["HumanMessage", "AIMessage", "ToolMessage"]

    # 幂等：再同步不加重复
    mem.sync_session_messages(
        [HumanMessage(content="你好"), AIMessage(content="你好！")],
        reason="test2",
    )
    assert len(mem._load_session_doc(mem._current_session)["messages"]) == 3

    mem.MEMORY_DIR, mem.MEMORY_FILE, mem.STATE_FILE = old_dir, old_file, old_state
    mem._current_session = None


if __name__ == "__main__":
    test_import_packages()
    test_compact_under_limit_noop()
    test_compact_over_limit_keeps_humans_and_recent_ai()
    test_session_json_sync()
    print("tests OK")
