# -*- coding: utf-8 -*-
"""
卡券集市 · 全站比价 —— 自动更新服务（零依赖，仅 Python 标准库）

职责：
  1. 提供静态站点（./index.html、./assets、./data）
  2. 后台定时重抓 kaquanjishi.com 并覆盖 ./data（默认每 REFRESH_MINUTES 分钟一轮）
  3. 对外暴露状态：
       GET  /api/status   当前数据版本 / 是否正在刷新 / 进度 / 错误
       POST /api/refresh  手动触发一次刷新（异步，立即返回）

环境变量：
  PORT              监听端口（默认 8801，线上由平台注入）
  REFRESH_MINUTES   定时刷新间隔，分钟（默认 40）
  STALE_MINUTES     数据超过该时长时，页面访问会触发一次后台刷新（默认 20）
"""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.join(HERE, "pipeline")
CACHE = os.path.join(HERE, "cache")
WORK = os.path.join(CACHE, "work")
STATE = os.path.join(CACHE, "state.json")

PORT = int(os.environ.get("PORT") or "8801")
HOST = os.environ.get("HOST") or "0.0.0.0"
INTERVAL_MIN = max(5, int(os.environ.get("REFRESH_MINUTES") or "40"))
STALE_MIN = max(2, int(os.environ.get("STALE_MINUTES") or "20"))

os.makedirs(WORK, exist_ok=True)

LOCK = threading.Lock()
S = {
    "version": 0,
    "updated": None,      # 站点数据时间（人读）
    "last_ok": 0,         # 上次成功刷新的 epoch
    "last_attempt": 0,    # 上次尝试刷新的 epoch（无论成败，用于控频）
    "running": False,
    "progress": "",
    "last_error": "",
    "rounds": 0,
    "trigger": "",
}


def log(*a):
    print("[server]", *a, flush=True)


def save():
    try:
        json.dump(S, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception as e:
        log("state 写入失败:", e)


def load():
    got = False
    try:
        S.update(json.load(open(STATE, encoding="utf-8")))
        got = True
    except Exception:
        pass
    if not got:
        # 首次部署（没有 state.json）：以已随包发布的站点数据时间为基准，
        # 否则 last_ok=0 会被判定为"永远过期"，服务一启动就立刻重抓一轮。
        try:
            m = json.load(open(os.path.join(HERE, "data", "meta.json"), encoding="utf-8"))
            S["updated"] = m.get("generated")
            S["last_ok"] = time.time()
            S["last_attempt"] = time.time()
            log("首次启动：以随包数据(%s)为基准，%d 分钟后再刷新" % (S["updated"], INTERVAL_MIN))
        except Exception:
            log("首次启动：无本地数据，将立即抓取一轮")
    S["running"] = False
    S["progress"] = ""


def run_refresh(why):
    if not LOCK.acquire(blocking=False):
        log("已在刷新中，跳过（%s）" % why)
        return False
    try:
        S["running"] = True
        S["progress"] = "启动抓取"
        S["trigger"] = why
        S["last_error"] = ""
        save()
        log("开始刷新（%s）" % why)

        env = dict(os.environ, KAQUAN_WORK=WORK)
        p = subprocess.Popen(
            [sys.executable, os.path.join(PIPE, "fetch.py")],
            cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1)

        for line in p.stdout:
            line = line.rstrip()
            if not line:
                continue
            if line.startswith("PROGRESS "):
                S["progress"] = line[9:]
            elif line.startswith("PUBLISH_SKIP"):
                S["progress"] = "本轮数据不完整，已保留上一版"
                log(line)
                continue
            elif line.startswith("PUBLISH "):
                S["progress"] = "正在整理数据…"
            elif line.startswith("START ") or line.startswith("TOKEN_OK"):
                S["progress"] = "已连接数据源"
            elif line.startswith("RATE "):
                S["progress"] = "源站限流，退避重试中…"
                log(line)
                continue
            elif line.startswith("FAIL"):
                S["last_error"] = line[:160]
                log(line)
                continue
            elif line.startswith("DONE"):
                S["progress"] = "收尾"
            else:
                log(line)
            save()
        p.wait()

        if p.returncode == 0:
            S["version"] += 1
            S["rounds"] += 1
            S["last_ok"] = time.time()
            S["updated"] = time.strftime("%Y-%m-%d %H:%M", time.localtime())
            log("刷新完成 v%d @ %s" % (S["version"], S["updated"]))
        elif p.returncode == 3:
            S["last_error"] = ""          # 数据不完整属可预期情况，不算错误
            log("本轮抓取不完整，已保留上一版数据")
        else:
            if not S["last_error"]:
                S["last_error"] = "抓取进程退出码 %s" % p.returncode
            log("刷新失败：%s" % S["last_error"])
    except Exception as e:
        S["last_error"] = str(e)[:160]
        log("刷新异常：", e)
    finally:
        S["running"] = False
        S["progress"] = ""
        S["last_attempt"] = time.time()
        save()
        LOCK.release()
    return True


def trigger(why):
    if S["running"]:
        return False
    threading.Thread(target=run_refresh, args=(why,), daemon=True).start()
    return True


def base_ts():
    """刷新节流基准：上次成功 与 上次尝试 中较晚者。

    关键作用：一轮抓取哪怕失败/不完整，也要等满一个周期才允许再试，
    避免"失败 → 立即重试 → 再失败"地持续轰炸源站。
    """
    return max(S.get("last_ok") or 0, S.get("last_attempt") or 0)


def due_in():
    b = base_ts()
    if not b:
        return 0
    return max(0, int(INTERVAL_MIN * 60 - (time.time() - b)))


def scheduler():
    time.sleep(6)
    while True:
        try:
            if not S["running"] and due_in() <= 0:
                trigger("定时")
        except Exception as e:
            log("调度异常:", e)
        time.sleep(60)


def status():
    last = S.get("last_ok") or 0
    return {
        "version": S["version"],
        "updated": S["updated"],
        "lastOk": last,
        "running": S["running"],
        "progress": S["progress"],
        "lastError": S["last_error"],
        "rounds": S["rounds"],
        "intervalMin": INTERVAL_MIN,
        "staleMin": STALE_MIN,
        "nextIn": due_in(),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/status":
            # 数据过旧时，访问即触发一次后台刷新；但距上次尝试不足 10 分钟则不重复触发
            last = S.get("last_ok") or 0
            att = S.get("last_attempt") or 0
            if (not S["running"] and (time.time() - last) > STALE_MIN * 60
                    and (time.time() - att) > 600):
                trigger("页面访问")
            return self._json(status())
        if path == "/api/refresh":
            ok = trigger("手动")
            return self._json({"ok": ok, "running": S["running"], "status": status()})
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] == "/api/refresh":
            ok = trigger("手动")
            return self._json({"ok": ok, "running": S["running"], "status": status()})
        self.send_error(404)


def main():
    load()
    threading.Thread(target=scheduler, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    log("服务已启动 %s:%s，刷新间隔 %d 分钟，数据过期阈值 %d 分钟"
        % (HOST, PORT, INTERVAL_MIN, STALE_MIN))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
