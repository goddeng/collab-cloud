# Channels — 通知渠道库

> 把团队事件推送到外部通信平台（钉钉、飞书、邮件、Slack ...）的可复用 lib。

## 状态

📋 **Phase 4 待实现**（钉钉单向 → 双向 → 飞书 → 其他）

## 抽象

```python
class Channel(ABC):
    type_id: str       # "dingtalk" / "feishu" / "email" / ...
    config_schema: dict  # 该 channel 的配置 schema (用于 UI 表单生成)

    @abstractmethod
    def notify(self, event: Event) -> NotifyResult:
        """把事件推到外部信道（fire-and-forget）"""

    @abstractmethod
    def test(self) -> bool:
        """连通性测试"""

    # 可选：对话式（双向）
    def receive_callback(self, raw: dict) -> Optional[Command]:
        """如果该 channel 支持双向，解析 inbound 事件成命令"""
        return None
```

## 事件类型

```python
@dataclass
class Event:
    type: str          # task_assigned | task_accepted | task_update | task_completed | ...
    project_id: str
    project_name: str
    actor: str         # who did it
    target: str        # who receives it
    task_id: str | None
    task_title: str | None
    text: str          # human-readable summary
    payload: dict      # full structured data
```

## 计划目录

```
packages/channels/
├── pyproject.toml
├── src/channels/
│   ├── __init__.py
│   ├── base.py             # Channel ABC + Event
│   ├── registry.py         # 注册表
│   ├── dingtalk.py         # 钉钉自定义机器人 + 企业内部应用
│   ├── feishu.py           # 飞书机器人 + 自建应用
│   ├── email.py            # SMTP 简单通知
│   └── slack.py            # （未来）
└── tests/
```

## 设计原则

1. **fan-out 不阻塞** — Channel 推送失败不影响主消息流
2. **可测试** — 每个 channel 提供 dry-run mode
3. **配置即代码** — channel 配置通过 JSON Schema 自描述，UI 自动生成表单
4. **复用** — 这个 lib 同时被 collab 本地版和 collab-cloud 调用
