FROM python:3.11-slim

WORKDIR /app

# 系统依赖最小
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV RELAY_HOST=0.0.0.0 \
    RELAY_PORT=8080 \
    RELAY_DB=/data/teams.db \
    RELAY_LOG_LEVEL=INFO

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["python", "-u", "relay.py"]
