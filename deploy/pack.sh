#!/usr/bin/env bash
# 打包自托管部署包
#   产物1  dist/kaquan-selfhost/            目录（Docker build 的上下文）
#   产物2  dist/kaquan-selfhost.tar.gz      上传到服务器的压缩包
#
# 用法： bash deploy/pack.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SITE="$ROOT/site"
DIST="$ROOT/dist"
OUT="$DIST/kaquan-selfhost"

echo "==> 清理旧产物"
rm -rf "$OUT" "$DIST/kaquan-selfhost.tar.gz"
mkdir -p "$OUT/app"

echo "==> 拷贝应用本体（不含可写缓存）"
for f in server.py index.html assets data pipeline; do
  cp -R "$SITE/$f" "$OUT/app/"
done
# 清掉可能被打进来的解释器缓存
find "$OUT/app" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> 拷贝热启动数据（首启导入，保证一上线就有完整数据）"
mkdir -p "$OUT/app/cache-seed"
if [ -d "$SITE/cache/work" ]; then
  cp -R "$SITE/cache/work" "$OUT/app/cache-seed/work"
fi

echo "==> 拷贝部署文件"
for f in Dockerfile entrypoint.sh docker-compose.yml Caddyfile nginx.conf kaquan.service .env.example README.md; do
  cp "$HERE/$f" "$OUT/$f"
done
chmod +x "$OUT/entrypoint.sh"

echo "==> 校验关键文件"
for f in app/server.py app/index.html app/data/meta.json app/pipeline/fetch.py \
         app/pipeline/analyze.py app/pipeline/build_web.py app/pipeline/keywords.json entrypoint.sh Dockerfile; do
  [ -e "$OUT/$f" ] || { echo "缺少 $f，打包中止"; exit 1; }
done
echo "  关键文件齐备"

echo "==> 压缩"
tar -czf "$DIST/kaquan-selfhost.tar.gz" -C "$DIST" kaquan-selfhost

echo ""
echo "完成："
du -sh "$OUT" "$DIST/kaquan-selfhost.tar.gz" 2>/dev/null || true
echo ""
echo "下一步：把 dist/kaquan-selfhost.tar.gz 传到服务器，见包里的 README.md"
