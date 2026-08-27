#!/usr/bin/env python3
"""Claude-code-mini CLI（LangChain create_agent · Phase B）。

用法（在工程根 claude-code-mini/ 下）：
  python main.py                         # 交互选择：新建或续聊
  python -m serve.main --new             # 强制新建
  python -m serve.main --session session_YYYYMMDD_...
  python serve/main.py --output-dir my_runs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]  # claude-code-mini/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import readline

    readline.parse_and_bind("set bind-tty-special-chars off")
    readline.parse_and_bind("set input-meta on")
    readline.parse_and_bind("set output-meta on")
    readline.parse_and_bind("set convert-meta off")
except ImportError:
    pass

from langchain_core.messages import AIMessage, HumanMessage

from agents.agent import build_agent
from harness import config as cfg
from harness.config import ensure_runtime_dirs, set_output_dir
from harness.memory import current_session_name, start_session


def print_assistant(messages: list) -> None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            content = msg.content
            if isinstance(content, list):
                texts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        texts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        texts.append(part)
                print("\n".join(texts))
            else:
                print(content)
            return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Claude-code-mini CLI")
    parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help="工具文件输出目录，写入 OUTPUT_DIR（默认 .output，也可用环境变量 OUTPUT_DIR）",
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--new", action="store_true", help="新建会话（跳过交互选择）")
    g.add_argument(
        "--session",
        metavar="NAME",
        default=None,
        help="续聊指定会话目录名，如 session_20260825_213400_997275",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    set_output_dir(args.output_dir)
    ensure_runtime_dirs()

    if args.new:
        start_session(source="cli", mode="new")
    elif args.session:
        start_session(source="cli", mode="resume", session_name=args.session)
    else:
        start_session(source="cli", mode="prompt")

    print("Claude-code-mini（Planner + Solver）")
    print(f"  OUTPUT_DIR: {cfg.OUTPUT_DIR}")
    print(f"  记忆目录: {cfg.MEMORY_DIR}")
    print(f"  thread_id: {cfg.THREAD_ID}")
    print(f"  本进程会话: .memory/{current_session_name()}/")
    print("  输入问题后回车；输入 q 退出。\n")

    agent = build_agent()
    config = {"configurable": {"thread_id": cfg.THREAD_ID}}

    while True:
        try:
            query = input("\033[36mmini >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if query.strip().lower() in ("q", "exit", "quit", ""):
            break
        try:
            result = agent.invoke(
                {"messages": [HumanMessage(content=query)]},
                config=config,
            )
            print_assistant(result["messages"])
            print()
        except Exception as e:
            print(f"\033[31m错误：{e}\033[0m\n")


if __name__ == "__main__":
    main()
