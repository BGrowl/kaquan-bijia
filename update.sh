#!/usr/bin/env bash
# 卡券集市 · 一键更新
#   抓取 kaquanjishi.com -> 清洗/比价 -> 生成静态分片 -> 发布到 surge.sh
#
# 用法： bash update.sh
#
# 这份脚本要同时跑在两个地方：
#   1) 本机 Windows 的 Git Bash（本地定时任务）
#   2) GitHub Actions 的 ubuntu-latest（7×24 云端）
# 所以解释器一律「探测」而不是写死路径。
#
# 可用环境变量覆盖：
#   KAQUAN_PY / KAQUAN_NODE / KAQUAN_SURGE   指定解释器与 surge CLI 路径
#   SURGE_TOKEN                              发布 token（云端从 Secrets 注入）
# 本机私有配置：同目录下的 .env.local（已 gitignore，不会入库）会被自动 source。
set -uo pipefail
cd "$(dirname "$0")"

ROOT="$(pwd)"
WORK="$ROOT/data"          # 原始抓取数据（kw_*.json / analysis.json）
PUB="$ROOT/public"         # 要发布的静态站目录
TOKEN_FILE="$ROOT/wrapper/.surge-token"

# 本机私有覆盖（不入库）：放只在本机存在的路径，例如 KAQUAN_SURGE=...
[ -f "$ROOT/.env.local" ] && . "$ROOT/.env.local"

PY="${KAQUAN_PY:-$(command -v python3 || command -v python || true)}"
NODE="${KAQUAN_NODE:-$(command -v node || true)}"
SURGE="${KAQUAN_SURGE:-$(command -v surge || true)}"

for pair in "KAQUAN_PY:$PY" "KAQUAN_NODE:$NODE" "KAQUAN_SURGE:$SURGE"; do
  if [ -z "${pair#*:}" ]; then
    echo "找不到 ${pair%%:*}：既不在 PATH 里，环境变量也没给。" >&2
    echo "本机请写进 $ROOT/.env.local，云端请检查 setup-python / setup-node / npm i -g surge。" >&2
    exit 1
  fi
done

export KAQUAN_WORK="$WORK"
export KAQUAN_DATA="$PUB/data"

ts() { date "+%Y-%m-%d %H:%M:%S"; }
echo "[$(ts)] 解释器：PY=$PY  NODE=$NODE  SURGE=$SURGE"
echo "[$(ts)] == 1/2 抓取数据源并生成站点分片 =="
"$PY" "$ROOT/site/pipeline/fetch.py"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "[$(ts)] 抓取阶段未成功（退出码 $rc），保留线上旧版本，不发布"
  exit "$rc"
fi

echo "[$(ts)] == 2/2 同步静态壳并发布到 kaquan-bijia.surge.sh =="
# 静态壳（assets/*）以 site/ 为准，每次发布前同步过去，免得改了前端忘了拷。
mkdir -p "$PUB/assets"
cp -f "$ROOT/site/assets/"* "$PUB/assets/"
# 首页不直接拷壳：由 build_shell.py 把 css + js + 首屏数据内联成单文件，
# 首屏只需 1 个请求（改造前 6 个请求且被一个 404 接口串行阻塞，手机端极慢）。
"$PY" "$ROOT/site/pipeline/build_shell.py" || { echo "[$(ts)] 内联首页失败，中止发布"; exit 1; }
echo "[$(ts)] 已同步 $(ls "$PUB/assets" | wc -l) 个静态资源 + 内联首页"

# token：优先环境变量（云端走 Secrets），否则读本机文件
if [ -z "${SURGE_TOKEN:-}" ]; then
  if [ -f "$TOKEN_FILE" ]; then
    SURGE_TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"
  else
    echo "[$(ts)] 缺少 surge token：\$SURGE_TOKEN 为空，且找不到 $TOKEN_FILE"
    exit 1
  fi
fi

cd "$PUB"
# surge 的输出先落到日志文件，成功才截尾显示，失败则打全量。
# 不能写成 `surge ... | tail -6` —— 管道后面再跟一条 echo，$? 就被 echo 覆盖了，
# 发布失败也会返回 0，云端 workflow 会显示"绿色成功"，是最危险的一类假成功。
LOGF="$ROOT/.publish.log"
NODE_OPTIONS=--dns-result-order=ipv4first \
SURGE_TOKEN="$SURGE_TOKEN" \
"$NODE" "$SURGE" . kaquan-bijia.surge.sh > "$LOGF" 2>&1
pub_rc=$?
if [ "$pub_rc" -ne 0 ]; then
  echo "[$(ts)] 发布失败（退出码 $pub_rc），线上仍是上一版。surge 输出如下："
  tail -40 "$LOGF"
  exit "$pub_rc"
fi
tail -6 "$LOGF"

echo "[$(ts)] 完成。数据时间：$(head -c 120 "$PUB/data/meta.json" | sed 's/.*"generated":"\([^"]*\)".*/\1/')"
