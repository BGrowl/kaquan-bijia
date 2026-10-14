# 卡券比价雷达 · 自托管镜像
# 零第三方依赖：只用 Python 标准库，因此镜像极小
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    PORT=8000 \
    REFRESH_MINUTES=40 \
    STALE_MINUTES=20

WORKDIR /app

# 应用本体（server.py / index.html / assets / data / pipeline）
COPY app/ /app/

# 可写缓存目录：在镜像阶段就建好，Docker 首次挂载卷时会继承它的属主，
# 否则具名卷会以 root 建目录，非 root 进程写不进去。
RUN useradd -m -u 10001 appuser \
 && mkdir -p /app/cache \
 && chown -R appuser:appuser /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=6s --start-period=15s --retries=3 \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/status',timeout=5)"

ENTRYPOINT ["/entrypoint.sh"]
