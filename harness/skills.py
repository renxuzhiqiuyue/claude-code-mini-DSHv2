"""技能扫描与加载：按角色扫 skills/{planner|solver}/ + skills/shared/。"""

from __future__ import annotations

from pathlib import Path

from harness.config import SKILLS_DIR

# role -> 相对 SKILLS_DIR 的子目录（专属在前，shared 在后；同名时专属优先）
_ROLE_BUCKETS: dict[str, tuple[str, ...]] = {
    "planner": ("planner", "shared"),
    "solver": ("solver", "shared"),
}

# role -> {skill_name: meta}
_REGISTRIES: dict[str, dict[str, dict]] = {"planner": {}, "solver": {}}


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    meta: dict = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, parts[2].strip()


def _scan_bucket(bucket: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not bucket.is_dir():
        return out
    for d in sorted(bucket.iterdir()):
        manifest = d / "SKILL.md"
        if not (d.is_dir() and manifest.exists()):
            continue
        raw = manifest.read_text(encoding="utf-8")
        meta, _body = _parse_frontmatter(raw)
        name = meta.get("name", d.name)
        out[name] = {
            "name": name,
            "description": meta.get("description", "（无描述）"),
            "content": raw,
            "path": str(manifest),
            "bucket": bucket.name,
        }
    return out


def scan_skills(role: str | None = None) -> dict[str, dict]:
    """扫描技能。role=planner|solver；None 时两边都扫。返回该 role 的注册表（None 则返回 solver∪planner 并集视图）。"""
    roles = [role] if role in _ROLE_BUCKETS else list(_ROLE_BUCKETS)
    for r in roles:
        merged: dict[str, dict] = {}
        for bucket_name in _ROLE_BUCKETS[r]:
            for name, meta in _scan_bucket(SKILLS_DIR / bucket_name).items():
                if name not in merged:
                    merged[name] = meta
        _REGISTRIES[r] = merged
    if role in _ROLE_BUCKETS:
        return _REGISTRIES[role]
    union: dict[str, dict] = {}
    for reg in _REGISTRIES.values():
        union.update(reg)
    return union


def list_skills_catalog(role: str = "planner") -> str:
    if role not in _ROLE_BUCKETS:
        role = "planner"
    if not _REGISTRIES.get(role):
        scan_skills(role)
    reg = _REGISTRIES.get(role) or {}
    if not reg:
        return "（暂无技能）"
    lines = []
    for s in reg.values():
        tag = s.get("bucket", "")
        suffix = f" 〔{tag}〕" if tag else ""
        lines.append(f"- **{s['name']}**{suffix}：{s['description']}")
    return "\n".join(lines)


def load_skill_content(name: str, role: str = "planner") -> str:
    if role not in _ROLE_BUCKETS:
        role = "planner"
    if not _REGISTRIES.get(role):
        scan_skills(role)
    reg = _REGISTRIES.get(role) or {}
    skill = reg.get(name)
    if not skill:
        available = ", ".join(reg.keys()) or "无"
        dirs = "+".join(_ROLE_BUCKETS[role])
        return f"错误：未找到技能「{name}」（可见 skills/{{{dirs}}}）。可用：{available}"
    return skill["content"]
