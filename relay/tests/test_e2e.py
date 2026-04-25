"""End-to-end test: 启动一个内嵌 relay, 模拟 Hub + 2 个 Client 互发消息."""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp
from aiohttp import web

from auth import make_jwt
from relay import make_app, load_config


TEAM_ID = "t-e2e"
TEAM_SECRET = "e2e-test-secret-32-bytes-min-value-pad-pad"
ADMIN_TOKEN = "e2e-admin-token-32-bytes-min-aaaaaaa"


async def _ws_recv_until(ws, predicate, timeout=2.0):
    """Read frames until predicate(msg) is True or timeout."""
    deadline = time.time() + timeout
    collected = []
    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.receive(), timeout=deadline - time.time())
        except asyncio.TimeoutError:
            return collected, None
        if raw.type != aiohttp.WSMsgType.TEXT:
            continue
        msg = json.loads(raw.data)
        collected.append(msg)
        if predicate(msg):
            return collected, msg
    return collected, None


async def _start_relay():
    """Start an in-process relay server, return (port, runner, tmp_path)."""
    # 注意: 不用 `with TemporaryDirectory` 否则函数返回时目录被删, 导致 SQLite 无法写
    tmp = tempfile.mkdtemp(prefix="relay-e2e-")
    os.environ["RELAY_ADMIN_TOKEN"] = ADMIN_TOKEN
    os.environ["RELAY_DB"] = f"{tmp}/teams.db"
    config = load_config(None)
    app = make_app(config)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return port, runner, tmp


async def run():
    port, runner, tmp = await _start_relay()
    base_http = f"http://127.0.0.1:{port}"
    base_ws = f"ws://127.0.0.1:{port}"

    try:
        async with aiohttp.ClientSession() as http:
            # 1. health
            async with http.get(f"{base_http}/health") as r:
                assert r.status == 200
                body = await r.json()
                assert body["status"] == "ok"
            print("✅ health ok")

            # 2. register team
            async with http.post(
                f"{base_http}/admin/register-team",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                json={"team_id": TEAM_ID, "team_secret": TEAM_SECRET},
            ) as r:
                assert r.status == 200, await r.text()
            print("✅ team registered")

            # 3. unauthorized
            async with http.post(
                f"{base_http}/admin/register-team",
                headers={"Authorization": "Bearer wrong"},
                json={"team_id": "x", "team_secret": "y" * 32},
            ) as r:
                assert r.status == 401
            print("✅ admin auth enforced")

            # 4. Connect Hub + 2 Clients
            hub_jwt = make_jwt({"tid": TEAM_ID, "kind": "hub"}, TEAM_SECRET)
            alice_jwt = make_jwt({"tid": TEAM_ID, "kind": "client", "mid": "alice"}, TEAM_SECRET)
            bob_jwt = make_jwt({"tid": TEAM_ID, "kind": "client", "mid": "bob"}, TEAM_SECRET)

            hub_ws = await http.ws_connect(
                f"{base_ws}/ws/hub?team_id={TEAM_ID}",
                headers={"Authorization": f"Bearer {hub_jwt}"},
            )
            print("✅ hub connected")

            alice_ws = await http.ws_connect(
                f"{base_ws}/ws/client?team_id={TEAM_ID}&mid=alice",
                headers={"Authorization": f"Bearer {alice_jwt}"},
            )
            print("✅ alice connected")

            # Hub should receive system event "member_online" for alice
            _, sys_msg = await _ws_recv_until(
                hub_ws, lambda m: m.get("type") == "system" and m.get("event") == "member_online"
            )
            assert sys_msg, "hub did not receive member_online"
            assert sys_msg["mid"] == "alice"
            print("✅ hub got member_online for alice")

            bob_ws = await http.ws_connect(
                f"{base_ws}/ws/client?team_id={TEAM_ID}&mid=bob",
                headers={"Authorization": f"Bearer {bob_jwt}"},
            )

            # alice should receive system event "hub_online" (was emitted on hub connect)
            # but alice connected after hub, so alice missed it. That's expected.
            # Just drain alice's queue:
            await asyncio.sleep(0.05)

            # 5. Hub sends task to alice
            await hub_ws.send_json({
                "type": "msg",
                "id": "msg-1",
                "from": "hub",
                "to": "alice",
                "payload": {"task_id": "TASK-1", "title": "do something"},
            })

            _, recv = await _ws_recv_until(
                alice_ws, lambda m: m.get("type") == "msg" and m.get("payload", {}).get("task_id") == "TASK-1"
            )
            assert recv, "alice did not receive task"
            assert recv["from"] == "hub"
            print("✅ alice received task from hub")

            # 6. Alice replies to hub
            await alice_ws.send_json({
                "type": "msg",
                "id": "msg-2",
                "from": "alice",  # will be overridden by relay
                "to": "hub",
                "payload": {"action": "accept", "task_id": "TASK-1"},
            })

            _, reply = await _ws_recv_until(
                hub_ws, lambda m: m.get("type") == "msg" and m.get("payload", {}).get("action") == "accept"
            )
            assert reply, "hub did not receive reply"
            assert reply["from"] == "alice"
            print("✅ hub got reply from alice")

            # 7. Broadcast: hub sends to '*'
            await hub_ws.send_json({
                "type": "msg", "id": "msg-3", "from": "hub", "to": "*",
                "payload": {"announce": "team meeting in 5"},
            })

            _, alice_got = await _ws_recv_until(
                alice_ws, lambda m: m.get("payload", {}).get("announce") == "team meeting in 5"
            )
            _, bob_got = await _ws_recv_until(
                bob_ws, lambda m: m.get("payload", {}).get("announce") == "team meeting in 5"
            )
            assert alice_got and bob_got, "broadcast failed"
            print("✅ broadcast delivered to alice + bob")

            # 8. Send to offline carol → buffered
            await hub_ws.send_json({
                "type": "msg", "id": "msg-4", "from": "hub", "to": "carol",
                "payload": {"x": 1},
            })
            await asyncio.sleep(0.05)

            # Connect carol — should receive buffered msg
            carol_jwt = make_jwt({"tid": TEAM_ID, "kind": "client", "mid": "carol"}, TEAM_SECRET)
            carol_ws = await http.ws_connect(
                f"{base_ws}/ws/client?team_id={TEAM_ID}&mid=carol",
                headers={"Authorization": f"Bearer {carol_jwt}"},
            )
            _, carol_got = await _ws_recv_until(
                carol_ws, lambda m: m.get("payload", {}).get("x") == 1
            )
            assert carol_got, "buffered msg not flushed"
            print("✅ buffered msg delivered after carol connected")

            # 9. Wrong token rejected
            bad_ws = None
            try:
                bad_ws = await http.ws_connect(
                    f"{base_ws}/ws/client?team_id={TEAM_ID}&mid=mallory",
                    headers={"Authorization": "Bearer not-a-jwt"},
                )
                assert False, "expected 403 but got connection"
            except aiohttp.WSServerHandshakeError as e:
                assert e.status == 403
                print("✅ invalid token → 403")

            # Cleanup
            for ws in (hub_ws, alice_ws, bob_ws, carol_ws):
                await ws.close()

    finally:
        await runner.cleanup()
        # cleanup tempdir
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run())
    print("\n🎉 All e2e tests passed!")
