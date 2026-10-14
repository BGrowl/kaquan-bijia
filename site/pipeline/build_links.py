# -*- coding: utf-8 -*-
"""为「聚合站的每条商品记录」建立 -> 「商家官网商品页」的直接链接索引。

输入:
  data/analysis.json            抓取+清洗后的比价数据
  site/pipeline/sites.json      商家站 base（37 家）
输出:
  <WORK>/links.json             站点 id -> 品类 -> 归一化商品名 -> [{u,p}, ...]

用法:
  KAQUAN_WORK=<原始数据目录> python build_links.py
说明:
  商家接口有缓存（site/pipeline/cache/goods/），默认 24 小时过期，避免每轮更新都全量重拉。
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import goods_api as G  # noqa: E402

WORK = os.environ.get("KAQUAN_WORK") or os.path.join(os.path.dirname(HERE), "..", "data")
CACHE = os.path.join(HERE, "cache", "goods")
TTL_H = float(os.environ.get("KAQUAN_LINK_TTL_HOURS") or 24)

# 批量建索引属于"尽力而为"：单个请求缩短超时、不重试，
# 避免个别已经挂掉的商家站把 8 个 worker 全部拖住（曾导致整轮卡死十几分钟）。
G.TIMEOUT = int(os.environ.get("KAQUAN_LINK_TIMEOUT") or 12)
G.RETRY = int(os.environ.get("KAQUAN_LINK_RETRY") or 1)
# 已知死站/长期连不上的商家，直接跳过（当前仅「西柠檬权益」(35)，官网已无法访问）
SKIP_SITES = set(x.strip() for x in
                 (os.environ.get("KAQUAN_LINK_SKIP") or "35").split(",") if x.strip())
# 商品详情页需要登录的商家：不建商品直链，让前端退化为「站内搜索」
# （实测：商品页弹登录框，比"落到搜索结果页"体验更差。当前仅「优享票易」(96)）
LOGIN_SITES = set(x.strip() for x in (os.environ.get("KAQUAN_LINK_LOGIN_SITES") or "96").split(",") if x.strip())
# 某商家连续失败这么多次后，直接放弃该商家，不再浪费额度
FAIL_BREAK = int(os.environ.get("KAQUAN_LINK_FAIL_BREAK") or 6)

os.makedirs(CACHE, exist_ok=True)
_lock = threading.Lock()


def cache_path(sid, kw):
    safe = "".join(ch if ch.isalnum() else "_" for ch in kw)
    return os.path.join(CACHE, "%s__%s.json" % (sid, safe))


def load_cached(sid, kw):
    p = cache_path(sid, kw)
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return None
    if time.time() - (d.get("ts") or 0) > TTL_H * 3600:
        return None
    return d.get("products")


def save_cached(sid, kw, products):
    p = cache_path(sid, kw)
    with _lock:
        json.dump({"ts": time.time(), "products": products},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False)


def main():
    ana = json.load(open(os.path.join(WORK, "analysis.json"), encoding="utf-8"))
    sites = json.load(open(os.path.join(HERE, "sites.json"), encoding="utf-8"))

    # 收集需要处理的 (site_id, kw, system)
    need = {}
    for s in ana["specs"]:
        for r in s["rows"]:
            sid = r["site_id"]
            st = sites.get(str(sid)) or {}
            base = st.get("base")
            system = r.get("system")
            if base and system and str(sid) not in SKIP_SITES and str(sid) not in LOGIN_SITES:
                need.setdefault(sid, {}).setdefault(s["kw"], system)

    total_pairs = sum(len(v) for v in need.values())
    print("需要建索引: %d 家商家 / %d 个 (商家,品类) 组合" % (len(need), total_pairs))

    links = {}
    stat = {"ok": 0, "cached": 0, "fail": 0, "prods": 0}
    done = [0]

    def work(sid):
        st = sites.get(str(sid)) or {}
        base = st.get("base")
        out = {}
        streak = 0                                   # 连续失败计数
        for kw, system in list(need[sid].items()):
            prods = load_cached(sid, kw)
            if prods is None:
                try:
                    prods = G.fetch_products(system, base, kw)
                    save_cached(sid, kw, prods)
                    stat["ok"] += 1
                    streak = 0
                except Exception as e:                      # noqa: BLE001
                    stat["fail"] += 1
                    streak += 1
                    with _lock:
                        done[0] += 1
                    print("  FAIL %-16s %-8s %s" % (st.get("name", sid)[:16], kw,
                                                    str(e)[:70]))
                    if streak >= FAIL_BREAK:
                        print("  放弃 %-16s（连续 %d 次失败，判定为死站/不可用）"
                              % (st.get("name", sid)[:16], streak))
                        break
                    continue
                time.sleep(0.15)
            else:
                stat["cached"] += 1
            stat["prods"] += len(prods)
            idx = {}
            for p in prods:
                k = G.norm_name(p["name"])
                if not k:
                    continue
                idx.setdefault(k, []).append({"u": p["url"], "p": p["price"]})
            out[kw] = idx
            with _lock:
                done[0] += 1
                if done[0] % 50 == 0:
                    print("  进度 %d/%d" % (done[0], total_pairs))
        return sid, out

    with ThreadPoolExecutor(max_workers=8) as ex:
        for sid, out in ex.map(work, list(need.keys())):
            if out:
                links[str(sid)] = out

    dst = os.path.join(WORK, "links.json")
    json.dump(links, open(dst, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print("写入 %s  (%.1f MB)" % (dst, os.path.getsize(dst) / 1024 / 1024))
    print("商家接口: 新拉 %d / 缓存命中 %d / 失败 %d ；累计商品 %d 个"
          % (stat["ok"], stat["cached"], stat["fail"], stat["prods"]))
    print("覆盖 %d 家商家" % len(links))


if __name__ == "__main__":
    main()
