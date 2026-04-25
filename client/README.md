# Remote Client

> 让远程机器上的成员加入团队，通过 Relay 接收任务。

## 状态

📋 **Phase 3 待实现**（先做形态 A：被动消息中继）

## 形态选项

### 形态 A：被动消息中继（v1 起步）

```
collab-client daemon ──WS──▶ Relay
       │
       ▼
   ~/.collab/inbox/   + 桌面通知 + localhost API
       │
       ▲
   alice 自己 iTerm2 里跑 claude
   用 team.sh 命令通过 daemon 转发
```

### 形态 B：半自动 GUI

daemon 收到任务 → AppleScript 自动起 iTerm2 + claude，注入消息

### 形态 C：全自动 Headless

daemon 自己 spawn `claude` 子进程，无 GUI 依赖（适合云服务器）

## 计划

```
client/
├── collab_client/
│   ├── __init__.py
│   ├── cli.py              # `collab-client join/start/status/logout`
│   ├── daemon.py           # 后台进程
│   ├── ws_client.py        # 长连 Relay
│   ├── local_api.py        # localhost:8765 给 team.sh 用
│   └── notifier.py         # 桌面通知
├── pyproject.toml
└── README.md
```

## 安装（计划）

```bash
pip install collab-client
collab-client join "<invite-string>"
collab-client start  # daemon
```

## 跨平台支持

| 平台 | 形态 A | 形态 B | 形态 C |
|---|---|---|---|
| macOS | ✅ | ✅ | ✅ |
| Linux | ✅ | ❌ (无 AppleScript) | ✅ |
| Windows | ⏳ | ❌ | ⏳ |
