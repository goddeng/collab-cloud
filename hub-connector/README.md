# Hub Connector

> 把本地 [`multi-claude-collab`](https://github.com/goddeng/multi-claude-collab) Manager 的事件桥接到 Relay。

## 状态

📋 **Phase 2 待实现**

## 计划

```
hub-connector/
├── connector.py            # 主进程
├── webhook_server.py       # 接收 collab webhook (HTTP POST)
├── relay_client.py         # 上游连 Relay (WebSocket)
├── api_client.py           # 调 collab Manager API（处理远程成员命令回调）
├── config.example.yaml
└── tests/
```

## 工作原理

```
collab Manager  ──webhook──▶  Hub Connector  ──WSS──▶  Relay
                                    │
                                    ▼
                              远程客户端
```

- 监听本地 collab 的 webhook（任务创建/状态变化）
- 维护一个常连的 WSS 到 Relay
- 把 collab 事件序列化后通过 Relay 推给远程成员
- 反过来：远程成员通过 Relay 发来的命令 → 调用 collab Manager 的 HTTP API

## 对 collab 的最小改动（Phase 2 一并做）

在 collab `manager/server.py` 里添加：

```python
WEBHOOK_URLS = os.environ.get("COLLAB_WEBHOOKS", "").split(",")

def _emit_webhook(event_type: str, payload: dict):
    for url in WEBHOOK_URLS:
        if not url.strip(): continue
        try:
            requests.post(url, json={"type": event_type, **payload}, timeout=2)
        except Exception:
            pass

# 在 _push_to_member、任务状态变化处调用
```

不设环境变量 `COLLAB_WEBHOOKS` → collab 完全无变化。
