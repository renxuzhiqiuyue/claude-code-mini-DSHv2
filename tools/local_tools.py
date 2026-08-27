"""本地工具：当前日期（东八区）、安全数学计算器。"""

from __future__ import annotations

import ast
import json
import math
import operator
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

_TZ = ZoneInfo("Asia/Shanghai")

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "pow": math.pow,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        if name not in _FUNCS:
            raise ValueError(f"不允许的函数: {name}")
        args = [_eval_node(a) for a in node.args]
        return float(_FUNCS[name](*args))
    if isinstance(node, ast.Name) and node.id in ("pi", "e"):
        return float(getattr(math, node.id))
    raise ValueError(f"不支持的表达式节点: {type(node).__name__}")


def _safe_calc(expression: str) -> float:
    tree = ast.parse(expression.strip(), mode="eval")
    return _eval_node(tree)


@tool("current_date")
def current_date() -> str:
    """获取当前系统日期时间（东八区 Asia/Shanghai）。"""
    print("\033[33m→ current_date()\033[0m")
    now = datetime.now(_TZ)
    out = json.dumps(
        {
            "timezone": "Asia/Shanghai",
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "datetime": now.isoformat(timespec="seconds"),
            "weekday": now.strftime("%A"),
        },
        ensure_ascii=False,
        indent=2,
    )
    print(out)
    return out


@tool("calculator")
def calculator(expression: str) -> str:
    """数学计算器：四则运算、幂、取模，以及 sqrt/abs/pow/log/log10/exp；可用 pi、e。"""
    print(f"\033[33m→ calculator({expression!r})\033[0m")
    try:
        value = _safe_calc(expression)
        out = json.dumps(
            {"expression": expression, "result": value},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        out = json.dumps(
            {"expression": expression, "error": str(e)},
            ensure_ascii=False,
            indent=2,
        )
    print(out)
    return out


LOCAL_TOOLS = [
    current_date,
    calculator,
]
