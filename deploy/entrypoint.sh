#!/bin/sh
# 首次启动时把镜像内自带的热启动数据导入可写缓存目录。
# 这样即使挂载了一个空卷，站点也能立刻有完整数据；抓取失败的品类也有兜底数据源。
set -e

APP=/app
SEED="$APP/cache-seed"
CACHE="$APP/cache"

mkdir -p "$CACHE"

if [ -d "$SEED" ] && [ -z "$(ls -A "$CACHE" 2>/dev/null)" ]; then
  echo "[entry] 首次启动：导入热启动数据（约 3MB）..."
  cp -a "$SEED"/. "$CACHE"/
fi

echo "[entry] 启动服务：PORT=${PORT:-8000} REFRESH_MINUTES=${REFRESH_MINUTES:-40} STALE_MINUTES=${STALE_MINUTES:-20}"
exec python3 "$APP/server.py"
