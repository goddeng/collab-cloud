# collab-cloud — 架构设计

> 本文档描述**当前阶段（L3 联邦）**的具体架构。如果你想看更长远的愿景（L4 Mesh、Open Claude Federation），见 [VISION.md](./VISION.md)。

## 设计目标

1. **零业务数据上云** — 中继服务器不存任何项目/任务/成员内容
2. **轻量级部署** — 单 Docker 容器，单 VPS 可承载多个团队
3. **NAT 友好** — 所有连接走 HTTPS/WSS，无端口转发要求
4. **可扩展抽象** — Transport 和 Channel 双层抽象，易加新类型
5. **不破坏 collab 现有用户** — webhook 钩子向下兼容，可选启用

## 双层抽象

```
                 Manager Core (multi-claude-collab)
                         │
                         │ events (webhook)
                         ▼
                   Hub Connector
                         │
        ┌────────────────┴────────────────┐
        │                                 │
   Transports                         Channels
   (双向主通道，每成员 1 个)        (单向通知，每成员 N 个)
        │                                 │
   ┌────┼────┐                       ┌────┼────┐
   │    │    │                       │    │    │
 local rmt webhook                 钉钉  飞书  邮件
```

| 抽象 | 职责 | 数量 | 例 |
|---|---|---|---|
| **Transport** | 收消息 + 发回报（双向） | 每成员 1 个 | local（iTerm2）/ remote_http（远程客户端长轮询）|
| **Channel** | 单向广播通知 | 每成员 N 个 | 钉钉群 / 飞书 / 邮件 |

## 远程协作完整流程

### 1. Hub 注册团队

```
本地 Mac                                    Relay (云端)
  │                                            │
  │  POST /admin/register-team                 │
  │  { team_id, hash(team_secret) }            │
  │  ─────────────────────────────────────────▶│
  │                                            │
  │            { ok: true }                    │
  │  ◀─────────────────────────────────────────│
  │                                            │
  │  WS /ws/hub                                │
  │  Authorization: signed(team_secret)        │
  │  ═══════════════════════════════════════▶  │
  │                                            │
  │            (持久长连)                       │
```

### 2. 邀请远程成员

```
Hub                                         Relay
  │                                          │
  │ 1) 生成一次性 invite_token                │
  │    payload = { tid, mid, role, exp }     │
  │    sig = HMAC(team_secret, payload)      │
  │    invite = base64(payload + "." + sig)  │
  │                                          │
  │ 2) 把 invite 字符串通过任何渠道给 alice   │
  │    (钉钉/邮件/手抄都行)                   │
```

### 3. Remote Client 加入

```
Remote Client                                Relay
  │                                            │
  │  $ collab-client join <invite>             │
  │                                            │
  │  POST /api/v1/teams/{tid}/join             │
  │  { invite_token }                          │
  │  ─────────────────────────────────────────▶│
  │                                            │
  │  Relay 验证签名（用 hash(team_secret)）    │
  │  生成永久 member_token                     │
  │  通过 WS 通知 Hub: alice 想加入            │
  │                                            │
  │  Hub 回复 ack + 推送 team_brief            │
  │                                            │
  │            { member_token, brief }         │
  │  ◀─────────────────────────────────────────│
  │                                            │
  │  本地存 ~/.collab/<team>/credentials       │
```

### 4. 任务推送

```
bob 终端 (本地)    Hub Manager        Relay        alice client (远程)
   │                  │                │                │
   │ task new alice   │                │                │
   │ ──────────────▶  │                │                │
   │                  │ 写 tasks.json  │                │
   │                  │ webhook event  │                │
   │                  │ ──────▶ Hub Connector           │
   │                  │                │                │
   │                  │ Connector → WS │                │
   │                  │ ─────────────▶ │                │
   │                  │                │ 路由 to=alice  │
   │                  │                │ ─────────────▶ │
   │                  │                │                │
   │                  │                │  alice 收到 📨 │
```

### 5. Remote 反向操作

```
alice client            Relay              Hub Manager
   │                      │                     │
   │ collab-client task   │                     │
   │   accept TASK-001    │                     │
   │ ───WS ('to':'hub')──▶│                     │
   │                      │ 路由 (hub_only)     │
   │                      │ ──────────────────▶ │
   │                      │                     │
   │                      │   API 调用执行      │
   │                      │   写 tasks.json     │
   │                      │   webhook → push    │
   │                      │   to creator        │
```

## 数据所有权

| 数据 | 存放 |
|---|---|
| Projects, members, tasks, prompts | **Hub Manager** (本地) |
| Audit log | **Hub Manager** |
| Team-level secret | Hub + Relay (Relay 只存 hash) |
| Member token (signed) | Client + Hub (Relay 只验证签名) |
| In-flight messages | Relay (内存，60s buffer) |
| Connection state | Relay (内存) |

**Relay 完全不存业务数据**。重启 Relay 影响：
- ✅ 团队注册保留（SQLite，仅 team_id + secret_hash）
- ❌ 当前在线状态丢失 → Hub 和 Client 自动重连
- ❌ 60s buffer 中的消息丢失（Hub 已经持久化到 inbox 兜底）

## 鉴权模型

```
Team-level
  team_id:        e.g. t-abc123 (UUID)
  team_secret:    Hub 持有 + Relay 存 hash
  
Member-level (由 Hub 签发，Relay 仅验签)
  member_token = base64( payload || "." || HMAC(team_secret, payload) )
  payload = JSON({ "tid": "t-abc123", "mid": "alice", "exp": 1745683200, "role": "frontend" })

Hub-level (主连接)
  hub_token = signed JWT with team_secret
```

## 与 collab 的边界

| 数据流 | 谁主动 | 协议 |
|---|---|---|
| collab → cloud（事件外推）| collab | HTTP webhook (POST) |
| cloud → collab（远程成员动作）| hub-connector | HTTP API (collab 现有 endpoints) |

collab 的最小改动：在 `_push_to_member` 和任务状态变化处加 `_emit_webhook(event_type, payload)`。
不设环境变量 `COLLAB_WEBHOOKS` 时完全无影响。

## 安全威胁模型

| 威胁 | 缓解 |
|---|---|
| Relay 被入侵 | 业务数据不在 Relay；攻击者最多看到 team_id 和谁在线 |
| 邀请码泄露 | 一次性 + TTL（默认 1h）|
| 中间人窃听 | WSS (TLS 1.3) |
| 远程客户端冒充 | member_token 是 HMAC 签名，Relay 验签 |
| Hub 假冒 | team_secret 仅 Hub 持有 |
| 消息伪造 | 每条消息可由发送方签名（Phase 6 加）|

## 性能目标

| 指标 | 目标 |
|---|---|
| Hub → Client 端到端延迟 | < 200ms (同区域)，< 500ms (跨区域) |
| Relay 单实例支持团队数 | 100+ |
| Relay 单实例支持连接数 | 1000+ |
| 内存占用 | < 100MB |

## 参考实现技术栈

- **Relay**: Python 3.11 + `websockets` + SQLite
- **Hub Connector**: Python 3.11 + Flask (webhook 接收) + `websockets` (上 Relay)
- **Client**: Python 3.11 + Click (CLI) + `websockets`
- **Channel SDK**: Python 3.11 (各 channel 独立 module)
