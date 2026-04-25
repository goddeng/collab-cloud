# 安全设计

## 威胁模型

| ID | 威胁 | 影响 | 缓解 |
|---|---|---|---|
| T1 | Relay 被入侵 | Relay 端数据泄露 | 业务数据不存 Relay；最多看到 team_id 和谁在线 |
| T2 | 邀请码泄露 | 任意人加入团队 | 一次性 + TTL（默认 1h）|
| T3 | 中间人窃听 | 消息明文被截获 | 强制 WSS (TLS 1.3) |
| T4 | Remote Client 冒充 | 假装某成员 | member_token HMAC 签名，Relay 验签 |
| T5 | Hub 假冒 | 注入虚假任务 | team_secret 仅 Hub 持有 |
| T6 | 消息伪造 | Relay 篡改消息 | （Phase 6）Hub 端到端签名 |
| T7 | DoS 攻击 Relay | 服务不可用 | Rate limiting + IP 黑名单 |
| T8 | 团队成员越权操作 | 普通成员伪装 Leader | Manager 端权限校验（已有 `_require_leader_if_actor`）|
| T9 | 长 Token 泄露 | 长期被冒充 | Token TTL + 可主动撤销 |

## 信任边界

```
[ Hub Manager ]  ←→  [ Relay ]  ←→  [ Remote Client ]
   trusted           半信任             不可信
   (你的 Mac)        (云服务器)          (远程)
```

- **Hub Manager**：完全可信，所有真相源
- **Relay**：路由责任，但**不应**解析业务数据；业务密钥仅持有 hash
- **Remote Client**：登录后授权，但消息签名由 Hub 端验证（Relay 只做转发）

## 关键密钥层级

```
team_secret  (Hub-side, 不上 Relay)
    │
    ├── HMAC-derive ─→ hub_jwt        (Hub 自用)
    ├── HMAC-derive ─→ member_token   (签发给 Client)
    └── HMAC-derive ─→ invite_token   (一次性邀请)

team_secret 的 hash 存于 Relay (用于验证签名，但不能反推 secret 本身)
```

## 端到端加密 (Phase 6)

未来在消息层加 AES-GCM：

```
plaintext  → encrypt(member_pubkey) → ciphertext → Relay → decrypt(privkey)
```

每个成员（Hub + Client）都生成密钥对，公钥通过 Hub 分发。Relay 完全看不到明文。

## 已知风险（暂不缓解）

- **元数据可见**：Relay 可看到"alice 给 bob 发了一条消息"（即使内容加密）。如果元数据敏感，可考虑混淆（后期）
- **Side channel**：消息长度、时序可能泄露信息。低优先级
- **物理访问**：Hub 机器被窃 = 全盘失守。靠 macOS 全盘加密兜底

## 部署 checklist

- [ ] Relay 必须用 HTTPS（TLS 1.3+）
- [ ] Relay admin_token 至少 32 字节随机
- [ ] team_secret 至少 32 字节随机
- [ ] Hub 端定期轮换 team_secret（推荐 90 天）
- [ ] Relay log 不记录消息 payload，只记 metadata
- [ ] Relay 限速：每 IP 每分钟 ≤ 60 条消息
- [ ] 失败超过 N 次的连接拉黑（防暴力）
