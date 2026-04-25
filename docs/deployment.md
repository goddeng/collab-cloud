# 部署指南

## Relay (云端)

### 用 Docker Compose 部署

```bash
git clone https://github.com/goddeng/collab-cloud
cd collab-cloud/relay

# 编辑配置
cp config.example.yaml config.yaml
nano config.yaml

# 启动
docker compose up -d

# 查日志
docker compose logs -f relay
```

### 前置 HTTPS

Relay 本身只跑 HTTP（默认 :8080）。建议在前面套 nginx / Caddy 提供 TLS：

#### Caddy 配置示例

```
relay.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Caddy 自动用 Let's Encrypt 签证书。

#### Nginx 配置示例

```nginx
server {
    listen 443 ssl http2;
    server_name relay.example.com;
    ssl_certificate     /etc/letsencrypt/live/relay.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/relay.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;       # WS 长连不要超时
    }
}
```

## Hub Connector (本地 Mac)

```bash
cd hub-connector
cp config.example.yaml config.yaml
# 编辑 config.yaml: relay_url, team_id, team_secret
python connector.py
```

## Remote Client (远程机器)

```bash
pip install collab-client    # （TODO: 发布到 PyPI）
collab-client join "<invite-string>"
collab-client start          # 后台运行
```

## 环境变量速查

### Relay

| 变量 | 默认 | 说明 |
|---|---|---|
| `RELAY_HOST` | `0.0.0.0` | 监听地址 |
| `RELAY_PORT` | `8080` | 监听端口 |
| `RELAY_DB` | `/data/teams.db` | SQLite 路径 |
| `RELAY_ADMIN_TOKEN` | (必填) | 管理 token，用于 register-team |
| `RELAY_LOG_LEVEL` | `INFO` | 日志级别 |

### Hub Connector

| 变量 | 默认 | 说明 |
|---|---|---|
| `RELAY_URL` | (必填) | `wss://relay.example.com` |
| `TEAM_ID` | (必填) | 自定义或 UUID |
| `TEAM_SECRET` | (必填) | 团队密钥（首次会注册到 Relay）|
| `COLLAB_API` | `http://127.0.0.1:7777` | 本地 collab Manager |

### Client

存在 `~/.collab/<team_id>/credentials.json`：

```json
{
  "team_id": "t-abc123",
  "relay_url": "wss://relay.example.com",
  "member_id": "alice",
  "member_token": "<jwt>"
}
```

由 `collab-client join` 自动创建，**勿手动改 / 勿提交到 git**。
