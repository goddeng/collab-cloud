# collab-cloud

> **让 Claude 之间的协作突破单机、组织、国界的边界。**
>
> 不是一个中心化的 "Claude 云"，而是一个任意节点都能加入的协作网格 —
> 像 HTTP 让网页互联、像 SMTP 让邮件互通，我们想做的是：**让全世界的 Claude 都能链接起来**。
>
> 完整愿景见 → [VISION.md](./VISION.md)

---

## 这个仓库做什么

基于 [`multi-claude-collab`](https://github.com/goddeng/multi-claude-collab) 的**远程协作 + 集成层**。让 Claude Code 团队可以跨机器、跨网络协作，并通过钉钉/飞书等渠道与外部世界对话。

这是上述愿景的 **L3 阶段（联邦）参考实现**。

## 🎯 这是什么

`multi-claude-collab` 是一个本地多 Claude 协作系统（一个 Mac 上多个 iTerm2 Tab 互相分派任务）。
但它**只能在一台机器上**跑。

`collab-cloud` 在它之上添加：

| 能力 | 说明 |
|---|---|
| 🌐 **远程成员加入** | 团队成员从任何地方接入（家里 Mac、Linux 服务器、云容器）|
| 🤖 **钉钉/飞书机器人** | 任务分派和完成自动推送到群，单向 → 双向 |
| 🔗 **轻量级中继** | Docker 部署的中继服务器，仅转发消息，不存业务数据 |

## 🏗️ 架构

```
┌──────────────────┐                                    ┌──────────────────┐
│   Hub Manager    │                                    │   Remote Client  │
│   (本地 Mac)     │                                    │   (远程任意机器) │
│                  │                                    │                  │
│  business data:  │                                    │  collab-client   │
│  - projects      │      ┌───────────────────┐         │  + claude session│
│  - tasks         │◄────►│   Relay Server    │◄───────►│                  │
│  - members       │      │   (云端，超轻)    │         │                  │
│  - audit         │      │                   │         │                  │
│                  │      │  仅转发消息       │         │                  │
└──────────────────┘      │  无业务逻辑       │         └──────────────────┘
       ↑                  │  无持久存储       │
       │                  └───────────────────┘
       │ webhook
       ↓                              ▲
┌──────────────────┐                  │
│  Hub Connector   │                  │
│  + Channels      │             多个远程成员可同时连
│  (钉钉/飞书...)  │
└──────────────────┘
```

详细见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

## 📦 项目组成

| 模块 | 角色 | 部署位置 |
|---|---|---|
| [`relay/`](./relay) | 中继服务器（WebSocket）| 云端（Docker）|
| [`hub-connector/`](./hub-connector) | 把本地 Manager 的事件桥到 Relay | 本地（Mac，和 Manager 同机）|
| [`client/`](./client) | 远程成员客户端 | 远程（任意机器）|
| [`packages/channels/`](./packages/channels) | 通知渠道库（钉钉/飞书/邮件）| 共享 lib |

## 🚀 快速试用（部署完成后）

```bash
# 1. 部署 Relay (任意 VPS)
cd relay && docker compose up -d

# 2. 在本地 Mac (已跑 multi-claude-collab) 启动 hub-connector
cd hub-connector
cp config.example.yaml config.yaml
# 编辑 config.yaml 填 relay URL + team_id
python connector.py

# 3. 在远程机器加入团队
pip install collab-client
collab-client join "<邀请字符串>"
collab-client start
```

## 🔐 安全模型

- **业务数据全部留在 Hub**（你的本地 Mac），Relay 永不持久化业务内容
- **WSS (TLS 1.3)** 全程加密
- **HMAC 签名 + JWT** 鉴权 Hub 和成员
- **未来**：消息层端到端加密（Hub 和 Client 各持密钥对，Relay 看不到明文）

详细见 [docs/security.md](./docs/security.md)。

## 📚 文档

- [ARCHITECTURE.md](./ARCHITECTURE.md) — 详细架构、组件交互、协议规范
- [docs/protocol.md](./docs/protocol.md) — Relay WebSocket 协议
- [docs/deployment.md](./docs/deployment.md) — Docker 部署与运维
- [docs/security.md](./docs/security.md) — 威胁模型与防护

## 🛣️ Roadmap

| Phase | 内容 | 状态 |
|---|---|---|
| 0 | 项目骨架 + CI + 安全防护 | ✅ |
| 1 | Relay 服务器 + Docker 部署 | ⏳ |
| 2 | Hub Connector + collab webhook 钩子 | ⏳ |
| 3 | Remote Client (形态 A：被动消息中继) | ⏳ |
| 4 | 钉钉 Channel (单向通知) | ⏳ |
| 5 | 钉钉双向 (在群里 @机器人 直接操作任务) | ⏳ |
| 6 | 端到端加密 | ⏳ |
| 7 | Web 端远程客户端 (无需装 CLI) | ⏳ |

## 关联仓库

- [`multi-claude-collab`](https://github.com/goddeng/multi-claude-collab) — 本地核心系统（必须先跑通它，本仓库才有意义）

## License

MIT (TBD)
