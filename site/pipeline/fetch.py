# -*- coding: utf-8 -*-
"""
卡券集市(kaquanjishi.com) 全站聚合查价抓取 —— 网站自动更新版

流程：逐关键词抓取 -> 全部抓完 -> analyze.py -> build_web.py（覆盖站点数据）
输出：逐行 PROGRESS / FAIL / PUBLISH / DONE，供 server.py 解析进度

环境变量：
  KAQUAN_WORK      原始抓取数据目录（默认 <本目录>/work）
  KAQUAN_KEYWORDS  关键词清单（默认 <本目录>/keywords.json）

说明：抓取失败的品类会保留上一轮的旧文件，避免该品类整块消失。
"""
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("KAQUAN_WORK") or os.path.join(HERE, "work")
KWFILE = os.environ.get("KAQUAN_KEYWORDS") or os.path.join(HERE, "keywords.json")
PY = sys.executable

BASE = "https://kaquanjishi.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BATCH = 30

os.makedirs(WORK, exist_ok=True)

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
token_holder = {"v": ""}


def log(*a):
    print(*a, flush=True)


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    return opener.open(req, timeout=timeout).read().decode("utf-8", "replace")


def refresh_token():
    html = _get(BASE + "/price-check")
    m = re.search(r'name="csrf-token"\s+content="([a-f0-9]+)"', html)
    if not m:
        m = re.search(r"CSRF_TOKEN\s*=\s*'([a-f0-9]+)'", html)
    if not m:
        raise RuntimeError("未找到 CSRF token")
    token_holder["v"] = m.group(1)
    return token_holder["v"]


def query(keyword, offset):
    body = urllib.parse.urlencode({"keyword": keyword, "offset": offset, "limit": BATCH}).encode()
    req = urllib.request.Request(BASE + "/price-check/query", data=body, headers={
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRF-TOKEN": token_holder["v"],
        "Referer": BASE + "/price-check",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    })
    return json.loads(opener.open(req, timeout=180).read().decode("utf-8", "replace"))


THROTTLE_HINT = ("频繁", "稍后", "稍候", "请慢", "too many", "rate limit", "429")


def call(keyword, offset, tries=6):
    """带退避重试的查询。

    源站有频控：返回 code=1 / msg='查询过于频繁，请稍后再试'。
    命中限流时不放弃，而是刷新 token + 指数退避（15/30/45/60/75s）后重试；
    其它错误短暂重试。这样整轮抓取不会被一次限流打断。
    """
    last = ""
    for attempt in range(tries):
        res = None
        try:
            res = query(keyword, offset)
        except Exception as e:
            last = "网络异常 %s" % str(e)[:80]
        if res is not None and res.get("code") == 0:
            return res
        msg = str((res or {}).get("msg") or last)
        last = "code=%s msg=%s" % ((res or {}).get("code"), msg)
        if any(h in msg for h in THROTTLE_HINT):
            wait = 15 * (attempt + 1)
            log("RATE %s 限流，等待 %ds 后重试" % (keyword, wait))
            time.sleep(wait)
        else:
            time.sleep(2 + attempt * 2)
        try:
            refresh_token()
        except Exception:
            pass
    raise RuntimeError("重试 %d 次仍失败: %s" % (tries, last[:110]))


def fetch_keyword(keyword):
    items, meta = [], {}
    offset, site_count = 0, None
    while True:
        res = call(keyword, offset)
        d = res["data"]
        meta = d
        items.extend(d.get("list") or [])
        if site_count is None:
            site_count = int(d.get("site_count") or 0)
        offset += BATCH
        if offset >= site_count:
            break
        time.sleep(1.5)
    return items, meta


def kw_file(kw):
    safe = re.sub(r"[^\w\u4e00-\u9fff]+", "_", kw).strip("_")
    return os.path.join(WORK, "kw_%s.json" % safe)


def publish():
    env = dict(os.environ, KAQUAN_WORK=WORK)
    # 必需步骤：清洗比价 -> 生成站点分片 -> 内联单文件首页
    # build_shell.py 把 css/js/首屏数据内联进 public/index.html，首屏只需 1 个请求；
    # 它读的是 site/ 下的源文件，不依赖 assets 是否已同步，因此放在这里也安全。
    for script in ("analyze.py", "build_links.py", "build_web.py", "build_shell.py"):
        r = subprocess.run([PY, os.path.join(HERE, script)], env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            # build_links / build_shell 是"锦上添花"：拿不到商品直链时前端会退化为站内搜索，
            # 内联失败时 update.sh 还会再补跑一次，都不应阻断整轮发布
            #（否则一次接口抖动就会让站点停更，线上留旧版即可）。
            if script in ("build_links.py", "build_shell.py"):
                log("PUBLISH_WARN %s 失败（降级继续）: %s"
                    % (script, (r.stderr or "").strip()[-200:]))
                continue
            log("PUBLISH_FAIL %s: %s" % (script, (r.stderr or "").strip()[-300:]))
            return False
    return True


def main():
    raw = json.load(open(KWFILE, encoding="utf-8"))
    kws = [(x["kw"] if isinstance(x, dict) else x) for x in raw]
    n = len(kws)
    log("START %d 个关键词" % n)

    try:
        refresh_token()
        log("TOKEN_OK")
    except Exception as e:
        log("FAIL token: %s" % e)
        return 1

    ok = 0
    for i, kw in enumerate(kws, 1):
        try:
            items, meta = fetch_keyword(kw)
            json.dump({"keyword": kw,
                       "meta": {k: v for k, v in meta.items() if k != "list"},
                       "items": items},
                      open(kw_file(kw), "w", encoding="utf-8"), ensure_ascii=False)
            ok += 1
            log("PROGRESS %d/%d %s %d条" % (i, n, kw, len(items)))
        except Exception as e:
            log("FAIL %d/%d %s %s" % (i, n, kw, str(e)[:120]))
            try:
                refresh_token()
            except Exception:
                pass
        time.sleep(2.5)          # 放慢节奏，规避源站频控

    # 保护：抓成功的太少时，宁可保留上一版数据，也不要用残缺结果覆盖线上
    need = max(3, int(n * 0.5))
    if ok < need:
        log("PUBLISH_SKIP 仅 %d/%d 个关键词成功（需≥%d），保留上一版数据" % (ok, n, need))
        log("DONE 抓取 %d/%d 未发布" % (ok, n))
        return 3

    log("PUBLISH 生成站点数据（成功 %d/%d）" % (ok, n))
    good = publish()
    log("DONE 抓取 %d/%d 发布%s" % (ok, n, "成功" if good else "失败"))
    return 0 if good else 2


if __name__ == "__main__":
    sys.exit(main())
