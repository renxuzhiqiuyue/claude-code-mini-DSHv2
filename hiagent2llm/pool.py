"""固定数量的 HiAgent 会话槽：启动时对齐 POOL_SIZE，请求期间加锁，用完 reset。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from hiagent2llm import config as cfg
from hiagent2llm import hiagent

logger = logging.getLogger("hiagent2llm.pool")


@dataclass
class Slot:
    conversation_id: str
    available: bool = True
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ConversationPool:
    def __init__(self) -> None:
        self._slots: list[Slot] = []
        self._idle: asyncio.Queue[Slot] = asyncio.Queue()
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        size = cfg.POOL_SIZE
        existing = await hiagent.list_conversations()
        keep = existing[:size]
        extra = existing[size:]
        for cid in extra:
            try:
                await hiagent.delete_conversation(cid)
            except Exception:
                logger.exception("启动时删除多余会话失败: %s", cid)
        while len(keep) < size:
            keep.append(await hiagent.create_conversation())
        self._slots = [Slot(conversation_id=cid) for cid in keep]
        for slot in self._slots:
            await self._idle.put(slot)
        self._started = True
        logger.info("session pool ready: %s slots", len(self._slots))

    async def acquire(self, timeout: float | None = 120.0) -> Slot:
        if not self._started:
            raise RuntimeError("会话池未启动")
        try:
            slot = await asyncio.wait_for(self._idle.get(), timeout=timeout)
        except asyncio.TimeoutError as e:
            raise RuntimeError("会话池繁忙：所有槽位都在使用中") from e
        await slot.lock.acquire()
        if not slot.available or not slot.conversation_id:
            slot.lock.release()
            raise RuntimeError("会话槽已失效，拒绝新建超出 POOL_SIZE 的会话")
        return slot

    async def finish(self, slot: Slot) -> None:
        """问完后 reset 再放回；reset 失败则作废该槽，不再 create 第三个。"""
        try:
            if not slot.available:
                return
            try:
                new_id = await hiagent.reset(slot.conversation_id)
                slot.conversation_id = new_id
            except Exception:
                slot.available = False
                slot.conversation_id = ""
                logger.exception(
                    "reset 失败，槽位作废（不再额外 create，以免打满名额）"
                )
        finally:
            if slot.lock.locked():
                slot.lock.release()
            if slot.available:
                await self._idle.put(slot)

    def alive_count(self) -> int:
        return sum(1 for s in self._slots if s.available)


pool = ConversationPool()
