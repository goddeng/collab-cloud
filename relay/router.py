"""In-memory message router.

每个团队的连接状态:
  - 1 个 Hub WebSocket
  - N 个 Client WebSocket (member_id -> ws)
  - Pending buffer: 60s 内对方下线时缓存的消息

路由规则:
  to == "hub"   → 推给该团队的 Hub
  to == "*"     → 广播给团队全体 (Hub + 所有 Client)
  to == "<mid>" → 推给该 member; 不在线则 buffer
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Any

from aiohttp import web


log = logging.getLogger("relay.router")

BUFFER_TTL_SECONDS = 60
BUFFER_MAX_PER_MEMBER = 200


class _PendingMsg:
    __slots__ = ("msg", "expires_at")

    def __init__(self, msg: dict, ttl: int = BUFFER_TTL_SECONDS):
        self.msg = msg
        self.expires_at = time.time() + ttl


class Router:
    """Owns connection state for *all* teams."""

    def __init__(self):
        # team_id -> Hub WebSocketResponse
        self._hubs: dict[str, web.WebSocketResponse] = {}
        # team_id -> {member_id -> WebSocketResponse}
        self._clients: dict[str, dict[str, web.WebSocketResponse]] = defaultdict(dict)
        # team_id -> {member_id -> deque[_PendingMsg]}
        self._buffer: dict[str, dict[str, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=BUFFER_MAX_PER_MEMBER))
        )
        self._lock = asyncio.Lock()

    # ---------- Hub registration ----------
    async def register_hub(self, team_id: str, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            existing = self._hubs.get(team_id)
            if existing and not existing.closed:
                # Old Hub still connected; new connection wins, kick old
                try:
                    await existing.close(code=1000, message=b"replaced by new hub")
                except Exception:
                    pass
            self._hubs[team_id] = ws
        log.info("hub registered: team=%s", team_id)
        # Notify clients
        await self._broadcast_system(team_id, {"event": "hub_online"})

    async def unregister_hub(self, team_id: str, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            if self._hubs.get(team_id) is ws:
                del self._hubs[team_id]
                log.info("hub unregistered: team=%s", team_id)
                fire = True
            else:
                fire = False
        if fire:
            await self._broadcast_system(team_id, {"event": "hub_offline"})

    def get_hub(self, team_id: str) -> web.WebSocketResponse | None:
        return self._hubs.get(team_id)

    # ---------- Client registration ----------
    async def register_client(
        self, team_id: str, member_id: str, ws: web.WebSocketResponse
    ) -> None:
        async with self._lock:
            existing = self._clients[team_id].get(member_id)
            if existing and not existing.closed:
                try:
                    await existing.close(code=1000, message=b"replaced")
                except Exception:
                    pass
            self._clients[team_id][member_id] = ws
            # flush any buffered messages
            buf = self._buffer[team_id].pop(member_id, None)
        log.info("client registered: team=%s mid=%s", team_id, member_id)

        if buf:
            now = time.time()
            for pending in list(buf):
                if pending.expires_at >= now:
                    try:
                        await ws.send_json(pending.msg)
                    except Exception:
                        log.warning("flush buffered msg failed: team=%s mid=%s", team_id, member_id)
                        break

        # Tell hub about online status
        hub = self._hubs.get(team_id)
        if hub and not hub.closed:
            try:
                await hub.send_json({"type": "system", "event": "member_online", "mid": member_id})
            except Exception:
                pass

    async def unregister_client(
        self, team_id: str, member_id: str, ws: web.WebSocketResponse
    ) -> None:
        async with self._lock:
            if self._clients[team_id].get(member_id) is ws:
                del self._clients[team_id][member_id]
                log.info("client unregistered: team=%s mid=%s", team_id, member_id)
                fire = True
            else:
                fire = False
        if fire:
            hub = self._hubs.get(team_id)
            if hub and not hub.closed:
                try:
                    await hub.send_json(
                        {"type": "system", "event": "member_offline", "mid": member_id}
                    )
                except Exception:
                    pass

    # ---------- Routing ----------
    async def route(self, team_id: str, msg: dict[str, Any]) -> dict:
        """Route a 'msg' frame to its destination(s). Returns delivery report."""
        to = msg.get("to")
        if not to:
            return {"ok": False, "reason": "missing 'to' field"}

        if to == "hub":
            return await self._send_to_hub(team_id, msg)
        if to == "*":
            return await self._broadcast(team_id, msg)
        return await self._send_to_member(team_id, to, msg)

    async def _send_to_hub(self, team_id: str, msg: dict) -> dict:
        hub = self._hubs.get(team_id)
        if not hub or hub.closed:
            return {"ok": False, "reason": "hub_offline"}
        try:
            await hub.send_json(msg)
            return {"ok": True, "to": "hub"}
        except Exception as e:
            log.warning("send to hub failed: %s", e)
            return {"ok": False, "reason": str(e)}

    async def _send_to_member(self, team_id: str, member_id: str, msg: dict) -> dict:
        ws = self._clients[team_id].get(member_id)
        if ws and not ws.closed:
            try:
                await ws.send_json(msg)
                return {"ok": True, "to": member_id, "delivered": "realtime"}
            except Exception as e:
                log.warning("send to client failed: %s", e)
        # Buffer for later flush on reconnect
        async with self._lock:
            self._buffer[team_id][member_id].append(_PendingMsg(msg))
        return {"ok": True, "to": member_id, "delivered": "buffered"}

    async def _broadcast(self, team_id: str, msg: dict) -> dict:
        targets = list(self._clients[team_id].values())
        hub = self._hubs.get(team_id)
        if hub:
            targets.append(hub)
        delivered = 0
        for ws in targets:
            if ws.closed:
                continue
            try:
                await ws.send_json(msg)
                delivered += 1
            except Exception:
                pass
        return {"ok": True, "to": "*", "delivered": delivered}

    async def _broadcast_system(self, team_id: str, payload: dict) -> None:
        sys_msg = {"type": "system", **payload}
        for ws in list(self._clients[team_id].values()):
            if ws.closed:
                continue
            try:
                await ws.send_json(sys_msg)
            except Exception:
                pass

    # ---------- Stats ----------
    def stats(self) -> dict:
        """For /admin/stats endpoint."""
        total_clients = sum(len(c) for c in self._clients.values())
        total_buffered = sum(
            sum(len(q) for q in m.values()) for m in self._buffer.values()
        )
        return {
            "teams": len(set(self._hubs) | set(self._clients)),
            "hubs_online": len(self._hubs),
            "clients_online": total_clients,
            "msgs_buffered": total_buffered,
        }
