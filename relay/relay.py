"""Relay — collab-cloud message router.

Endpoints:
  GET  /health                            - health check
  POST /admin/register-team               - admin: register/update a team
  GET  /admin/stats                       - admin: connection stats
  GET  /admin/teams                       - admin: list registered teams
  GET  /ws/hub?team_id=<tid>              - Hub Manager 长连接
  GET  /ws/client?team_id=<tid>&mid=<mid> - Remote Client 长连接

Auth:
  - /admin/*    需要 Header: Authorization: Bearer <admin_token>
  - /ws/hub     需要 Header: Authorization: Bearer <hub_jwt>     (HMAC with team_secret)
  - /ws/client  需要 Header: Authorization: Bearer <member_token> (HMAC with team_secret)

Message format (JSON over WebSocket):
  { "type": "msg|ping|pong|system",
    "id":   "<uuid>",
    "ts":   <unix ms>,
    "from": "<member_id|hub>",
    "to":   "<member_id|hub|*>",
    "payload": { ... } }
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sys
from pathlib import Path

import yaml
from aiohttp import WSMsgType, web

from auth import verify_jwt
from router import Router
from store import TeamStore


log = logging.getLogger("relay")

# ============================================================
# Config
# ============================================================
def load_config(path: str | None = None) -> dict:
    """Load YAML config; env vars override."""
    cfg: dict = {}
    if path and Path(path).exists():
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}

    # Env overrides
    cfg["host"] = os.environ.get("RELAY_HOST", cfg.get("host", "0.0.0.0"))
    cfg["port"] = int(os.environ.get("RELAY_PORT", cfg.get("port", 8080)))
    cfg["db_path"] = os.environ.get("RELAY_DB", cfg.get("db_path", "data/teams.db"))
    cfg["log_level"] = os.environ.get("RELAY_LOG_LEVEL", cfg.get("log_level", "INFO"))

    # Admin token: env > config > generate
    admin_token = os.environ.get("RELAY_ADMIN_TOKEN") or cfg.get("admin_token")
    if not admin_token:
        admin_token = secrets.token_urlsafe(32)
        log.warning("RELAY_ADMIN_TOKEN not set; generated ephemeral token: %s", admin_token)
    cfg["admin_token"] = admin_token

    return cfg


# ============================================================
# Auth helpers
# ============================================================
def _bearer(request: web.Request) -> str:
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        return h[7:].strip()
    return h.strip()


def _require_admin(request: web.Request) -> web.Response | None:
    if _bearer(request) != request.app["admin_token"]:
        return web.json_response({"error": "unauthorized"}, status=401)
    return None


# ============================================================
# Routes — REST
# ============================================================
async def health(request: web.Request) -> web.Response:
    return web.json_response(
        {"status": "ok", "version": "0.1.0", "stats": request.app["router"].stats()}
    )


async def register_team(request: web.Request) -> web.Response:
    if (err := _require_admin(request)) is not None:
        return err
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    team_id = (body.get("team_id") or "").strip()
    secret = (body.get("team_secret") or "").strip()
    if not team_id or not secret:
        return web.json_response(
            {"error": "team_id and team_secret are required"}, status=400
        )
    if len(secret) < 16:
        return web.json_response(
            {"error": "team_secret must be at least 16 chars"}, status=400
        )

    request.app["store"].register_team(team_id, secret)
    log.info("team registered: %s", team_id)
    return web.json_response({"ok": True, "team_id": team_id})


async def admin_stats(request: web.Request) -> web.Response:
    if (err := _require_admin(request)) is not None:
        return err
    return web.json_response(request.app["router"].stats())


async def admin_list_teams(request: web.Request) -> web.Response:
    if (err := _require_admin(request)) is not None:
        return err
    return web.json_response({"teams": request.app["store"].list_teams()})


async def admin_delete_team(request: web.Request) -> web.Response:
    if (err := _require_admin(request)) is not None:
        return err
    tid = request.match_info["tid"]
    deleted = request.app["store"].delete_team(tid)
    return web.json_response({"ok": deleted})


# ============================================================
# Routes — WebSocket (Hub)
# ============================================================
async def ws_hub(request: web.Request) -> web.WebSocketResponse | web.Response:
    team_id = request.query.get("team_id", "").strip()
    if not team_id:
        return web.json_response({"error": "team_id required"}, status=400)

    secret = request.app["store"].get_secret(team_id)
    if not secret:
        return web.json_response({"error": "team not registered"}, status=404)

    payload = verify_jwt(_bearer(request), secret)
    if not payload or payload.get("kind") != "hub" or payload.get("tid") != team_id:
        return web.json_response({"error": "invalid token"}, status=403)

    ws = web.WebSocketResponse(heartbeat=20.0)
    await ws.prepare(request)

    router: Router = request.app["router"]
    await router.register_hub(team_id, ws)

    try:
        async for raw in ws:
            if raw.type == WSMsgType.TEXT:
                await _handle_frame(router, team_id, "hub", raw.data)
            elif raw.type == WSMsgType.ERROR:
                log.warning("hub ws error: team=%s err=%s", team_id, ws.exception())
                break
    finally:
        await router.unregister_hub(team_id, ws)
    return ws


# ============================================================
# Routes — WebSocket (Client)
# ============================================================
async def ws_client(request: web.Request) -> web.WebSocketResponse | web.Response:
    team_id = request.query.get("team_id", "").strip()
    member_id = request.query.get("mid", "").strip()
    if not team_id or not member_id:
        return web.json_response({"error": "team_id and mid required"}, status=400)

    secret = request.app["store"].get_secret(team_id)
    if not secret:
        return web.json_response({"error": "team not registered"}, status=404)

    payload = verify_jwt(_bearer(request), secret)
    if (
        not payload
        or payload.get("kind") != "client"
        or payload.get("tid") != team_id
        or payload.get("mid") != member_id
    ):
        return web.json_response({"error": "invalid token"}, status=403)

    ws = web.WebSocketResponse(heartbeat=20.0)
    await ws.prepare(request)

    router: Router = request.app["router"]
    await router.register_client(team_id, member_id, ws)

    try:
        async for raw in ws:
            if raw.type == WSMsgType.TEXT:
                await _handle_frame(router, team_id, member_id, raw.data)
            elif raw.type == WSMsgType.ERROR:
                log.warning("client ws error: team=%s mid=%s err=%s", team_id, member_id, ws.exception())
                break
    finally:
        await router.unregister_client(team_id, member_id, ws)
    return ws


# ============================================================
# Frame handler
# ============================================================
async def _handle_frame(router: Router, team_id: str, sender: str, raw: str) -> None:
    """Parse one WS text frame and dispatch."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("invalid json from %s/%s: %s", team_id, sender, raw[:80])
        return

    msg_type = msg.get("type")
    if msg_type == "ping":
        # aiohttp's heartbeat handles low-level pings; this is app-level
        # We just ack; no need to route
        return

    if msg_type == "msg":
        # Override 'from' to the authenticated sender (prevent spoofing)
        msg["from"] = sender
        await router.route(team_id, msg)
        return

    log.debug("unknown msg type=%s from=%s/%s", msg_type, team_id, sender)


# ============================================================
# App factory
# ============================================================
def make_app(config: dict) -> web.Application:
    app = web.Application()
    app["config"] = config
    app["store"] = TeamStore(config["db_path"])
    app["router"] = Router()
    app["admin_token"] = config["admin_token"]

    app.router.add_get("/health", health)
    app.router.add_post("/admin/register-team", register_team)
    app.router.add_get("/admin/stats", admin_stats)
    app.router.add_get("/admin/teams", admin_list_teams)
    app.router.add_delete("/admin/teams/{tid}", admin_delete_team)
    app.router.add_get("/ws/hub", ws_hub)
    app.router.add_get("/ws/client", ws_client)
    return app


def main() -> int:
    cfg_path = os.environ.get("RELAY_CONFIG")
    config = load_config(cfg_path)

    logging.basicConfig(
        level=config["log_level"],
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    log.info(
        "Starting Relay on %s:%d (db=%s)",
        config["host"], config["port"], config["db_path"],
    )

    app = make_app(config)
    web.run_app(app, host=config["host"], port=config["port"], print=lambda _: None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
