# -*- coding: utf-8 -*-
"""为指定商家补齐「商品接口」缓存（供 build_links.py 快速组装索引）。

用法:
  python fill_cache.py <site_id> [<site_id> ...]

特点:
  - 只处理传入的商家，逐 (商家,品类) 组合拉取并写入 cache/goods/
  - 缩短超时、不重试，遇到死站快速放弃（避免个别站拖垮整轮）
  - 已缓存的组合直接跳过
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import goods_api as G  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
WORK = os.environ.get("KAQUAN_WORK") or os.path.join(ROOT, "data")
CACHE = os.path.join(HERE, "cache", "goods")
os.makedirs(CACHE, exist_ok=True)

# 补齐模式：快进快出
G.TIMEOUT = int(os.environ.get("FILL_TIMEOUT") or 8)
G.RETRY = int(os.environ.get("FILL_RETRY") or 1)
G.MAX_PAGE = int(os.environ.get("FILL_MAX_PAGE") or 4)


def cache_path(sid, kw):
    safe = "".join(ch if ch.isalnum() else "_" for ch in kw)
    return os.path.join(CACHE, "%s__%s.json" % (sid, safe))


def main(ids):
    ana = json.load(open(os.path.join(WORK, "analysis.json"), encoding="utf-8"))
    sites = json.load(open(os.path.join(HERE, "sites.json"), encoding="utf-8"))

    need = {}
    for s in ana["specs"]:
        for r in s["rows"]:
            sid = r["site_id"]
            if str(sid) not in ids:
                continue
            st = sites.get(str(sid)) or {}
            if st.get("base") and r.get("system"):
                need.setdefault(sid, {}).setdefault(s["kw"], r["system"])

    ok = cached = fail = 0
    prods = 0
    for sid, kws in need.items():
        st = sites.get(str(sid)) or {}
        base = (st.get("base") or "").rstrip("/")
        for kw, system in kws.items():
            p = cache_path(sid, kw)
            if os.path.exists(p):
                cached += 1
                continue
            try:
                ps = G.fetch_products(system, base, kw)
                json.dump({"ts": time.time(), "products": ps},
                          open(p, "w", encoding="utf-8"), ensure_ascii=False)
                ok += 1
                prods += len(ps)
            except Exception as e:                                   # noqa: BLE001
                fail += 1
                print("  FAIL %-14s %-10s %s" % (st.get("name", sid)[:14], kw,
                                                 str(e)[:60]), flush=True)
        print("  %-14s 完成（新拉 %d）" % (st.get("name", sid)[:14], ok), flush=True)
    print("汇总 %s：新拉 %d / 命中缓存 %d / 失败 %d / 商品 %d"
          % (",".join(ids), ok, cached, fail, prods), flush=True)


if __name__ == "__main__":
    main(set(sys.argv[1:]))
