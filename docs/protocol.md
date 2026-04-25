# Relay WebSocket 协议规范

> 本文档定义 Hub Manager / Remote Client 与 Relay 之间的通信协议。

## 连接

### Hub 连接

```
GET wss://relay.example.com/ws/hub?team_id=<tid>
Authorization: Bearer <hub_jwt>
```

`hub_jwt` 由 Hub 用 team_secret 签发：
```
header  = base64({"alg": "HS256", "typ": "JWT"})
payload = base64({"tid": "<tid>", "exp": <epoch>, "kind": "hub"})
sig     = HMAC_SHA256(team_secret, header + "." + payload)
hub_jwt = header + "." + payload + "." + sig
```

Relay 用 `hash(team_secret)` 验签的方式见下文。

### Client 连接

```
GET wss://relay.example.com/ws/client?team_id=<tid>&mid=<member_id>
Authorization: Bearer <member_token>
```

`member_token` 由 Hub 签发（同样用 team_secret），格式同 hub_jwt 但 `kind: "client"` 和带 `mid`。

## 消息格式

所有 WS frame 都是 JSON：

```jsonc
{
  "type": "msg",          // msg | ack | ping | pong | system
  "id":   "<uuid>",       // 幂等 ID
  "ts":   1745683200,     // unix ms
  "from": "bob",          // member_id 或 "hub"
  "to":   "alice",        // member_id 或 "hub" 或 "*" (broadcast)
  "payload": { ... }      // 业务数据，Relay 不解析
}
```

## 消息类型

### `msg` — 业务消息（最常见）

Relay 完全不解析 `payload`，只看 `to` 字段路由：
- `to: "<mid>"` → 发给该成员的 client
- `to: "hub"`   → 发给该团队的 Hub
- `to: "*"`     → 广播给所有连接的成员（包括 Hub）

如果 `to` 不在线：
- 60s 内 buffer 在内存
- 60s+ 后丢弃（Hub 端已经持久化到 inbox 兜底）

### `ack` — 确认

发送方可选请求 ack：

```json
{ "type": "msg", "id": "abc", "to": "alice", "ack_required": true }
```

接收方 client 处理完后回：
```json
{ "type": "ack", "id": "abc", "from": "alice", "to": "hub" }
```

### `ping` / `pong` — 心跳

每 20 秒发一次 ping，60 秒未收到 pong 则 Relay 关闭连接。

```json
{ "type": "ping", "ts": 1745683200 }
```

### `system` — 系统事件

Relay 主动通知，不路由：

```json
{ "type": "system", "event": "member_online", "mid": "alice" }
{ "type": "system", "event": "member_offline", "mid": "alice" }
{ "type": "system", "event": "hub_online" }
{ "type": "system", "event": "hub_offline" }
```

## REST API（带外操作）

### 注册团队（首次）

```
POST /admin/register-team
Authorization: Bearer <admin_token>   # Relay 自己的 admin token
Content-Type: application/json

{
  "team_id": "t-abc123",
  "secret_hash": "sha256(team_secret)"
}
```

### 加入团队（Client 用 invite）

```
POST /api/v1/teams/{team_id}/join
Content-Type: application/json

{
  "invite_token": "<base64-encoded payload + signature>"
}

→ 200 OK
{
  "member_token": "<long-lived token>",
  "team_brief": { ... }      // 由 Hub 通过 WS 实时返回
}
```

## 错误码

| Code | 描述 |
|---|---|
| 1008 | Policy violation (鉴权失败) |
| 1011 | Server error |
| 4001 | Team not registered |
| 4003 | Invalid signature |
| 4004 | Token expired |
| 4005 | Member not found in team |

## 协议版本

当前版本：`v1`

未来不兼容变更通过 URL 路径区分：`/ws/v2/hub` 等。
