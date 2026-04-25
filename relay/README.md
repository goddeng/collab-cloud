# Relay

> 极简 WebSocket 中继服务器。**不存业务数据**，只做转发。

## 状态

📋 **Phase 1 待实现**

## 计划技术栈

- Python 3.11
- `websockets` 库
- SQLite（仅存 team_id + secret_hash）
- Docker + docker-compose 部署

## 计划交付物

```
relay/
├── relay.py                # 主程序 (~200 行)
├── auth.py                 # JWT / HMAC 验证
├── routes.py               # REST endpoints (register-team / health)
├── ws.py                   # WebSocket handler
├── store.py                # SQLite 操作
├── config.example.yaml
├── Dockerfile
├── docker-compose.yml
├── tests/
└── README.md
```

## 设计参考

- [docs/protocol.md](../docs/protocol.md) — WebSocket 协议
- [docs/security.md](../docs/security.md) — 鉴权与威胁模型
- [docs/deployment.md](../docs/deployment.md) — 部署指南
