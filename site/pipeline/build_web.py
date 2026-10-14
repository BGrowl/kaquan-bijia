# -*- coding: utf-8 -*-
"""
把 data/analysis.json 转成静态网站用的分片数据 (web/data/*)

产物:
  web/data/meta.json       站点元信息 + 品类索引(首页用, 很小)
  web/data/merchants.json  商家榜
  web/data/cat/<i>.json    每个品类的完整数据(含各商家最低价 + 商品规格比价), 按需加载
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import goods_api as G  # noqa: E402

# 网站版：由 server.py 注入 KAQUAN_WORK(原始数据目录) 与 KAQUAN_DATA(网站数据目录)
WORK = os.environ.get("KAQUAN_WORK") or os.path.join(HERE, "work")
SRC = os.path.join(WORK, "analysis.json")
OUT = os.environ.get("KAQUAN_DATA") or os.path.join(HERE, "..", "data")
CATDIR = os.path.join(OUT, "cat")

os.makedirs(CATDIR, exist_ok=True)
# 注意：这里刻意不做"清空旧分片"的批量删除。
# 一次性删除 50+ 个文件会命中运行环境的删除保护闸门（SAFE_DELETE_BULK_CONFIRM_REQUIRED），
# 直接导致 build_web.py 返回非 0、整轮发布失败。
# 改为覆盖式写入：cat/<i>.json 每次都会被完整重写；即使某轮品类数变少，
# 多余的旧分片也不会出现在 meta.json 的 cats 里，前端按索引取数，不会被加载，无副作用。

a = json.load(open(SRC, encoding="utf-8"))
cats, specs, merchants = a["cats"], a["specs"], a["merchants"]

# ---------- 商家站映射（站点 id -> 官网 + 站内搜索模板）----------
# 由 _probe 探测得出：直接跳商家官网 / 官网搜索结果页，绕开聚合站的中转页。
SITES_FILE = os.path.join(HERE, "sites.json")
SITES = {}
if os.path.exists(SITES_FILE):
    SITES = json.load(open(SITES_FILE, encoding="utf-8"))

# ---------- 商品直链索引（聚合站记录 -> 商家官网商品页）----------
LINKS = {}
_lf = os.path.join(WORK, "links.json")
if os.path.exists(_lf):
    LINKS = json.load(open(_lf, encoding="utf-8"))


def link_for(sid, kw, name, price):
    """查该条记录在商家官网的商品页地址；查不到返回空串（前端会退化为站内搜索）"""
    d = LINKS.get(str(sid))
    if not d:
        return ""
    idx = d.get(kw)
    if not idx:
        return ""
    cands = idx.get(G.norm_name(name))
    if not cands:
        return ""
    if len(cands) == 1 or price is None:
        return cands[0]["u"]
    best, bd = None, None
    for c in cands:
        if c.get("p") is None:
            continue
        dd = abs(c["p"] - float(price))
        if bd is None or dd < bd:
            best, bd = c, dd
    return (best or cands[0])["u"]

GROUP_ORDER = ["视频会员", "音乐音频", "网盘阅读办公", "游戏点卡", "电商购物卡",
               "餐饮代下", "出行服务", "生活缴费"]


def r2(x):
    return round(float(x) + 1e-9, 2)


def pack_row(r, kw=None):
    """精简单条商品记录；u = 商家官网的商品详情/下单页直链（有则前端可一键直达）"""
    kw = kw if kw is not None else r.get("kw")
    return {
        "n": r["name"],
        "p": r2(r["price"]),
        "i": r["site_id"],
        "s": r["site_name"],
        "t": r.get("tag") or "",
        "u": link_for(r["site_id"], kw, r["name"], r["price"]),
    }


# 规格按品类归组
spec_by_kw = {}
for s in specs:
    spec_by_kw.setdefault(s["kw"], []).append(s)

# ---------- meta.json ----------
meta_cats = []
for idx, c in enumerate(cats):
    kw = c["keyword"]
    sl = spec_by_kw.get(kw, [])
    meta_cats.append({
        "i": idx,
        "kw": kw,
        "group": c["group"],
        "mc": c["merchant_count"],
        "lo": pack_row(c["cheapest"], kw),
        "sn": len(sl),
        "sc": sum(1 for x in sl if x["n"] >= 2),
    })

groups = []
for g in GROUP_ORDER:
    n = sum(1 for c in meta_cats if c["group"] == g)
    if n:
        groups.append({"name": g, "count": n})

meta = {
    "generated": time.strftime("%Y-%m-%d %H:%M"),
    "source": "kaquanjishi.com",
    "siteBase": "https://kaquanjishi.com/site/",
    "stats": {
        "cats": len(cats),
        "specs": len(specs),
        "comp": sum(1 for s in specs if s["n"] >= 2),
        "items": a["total_items"],
        "merchants": len(merchants),
    },
    "groups": groups,
    "cats": meta_cats,
}
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))

# ---------- merchants.json ----------
ms = []
for m in merchants:
    ms.append({
        "id": m["id"], "n": m["name"], "wins": m["wins"],
        "sw": m.get("spec_wins", 0), "appear": m["appear"],
        "top3": m["top3"], "cats": m["cats"],
    })
ms.sort(key=lambda x: (-x["wins"], -x["sw"], x["n"]))
json.dump(ms, open(os.path.join(OUT, "merchants.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))

# ---------- sites.json ----------
# n=商家名 b=官网 q=站内搜索模板（{kw} 占位） v=是否实测可直达
sites_out = {}
for sid, s in SITES.items():
    sites_out[str(sid)] = {
        "n": s.get("name") or "",
        "b": s.get("base") or "",
        "q": s.get("search") or "",
        "v": 1 if s.get("verified") else 0,
    }
json.dump(sites_out, open(os.path.join(OUT, "sites.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
_direct = sum(1 for s in sites_out.values() if s["q"] and s["v"])
print("sites.json    %6.1f KB (共 %d 家, 其中 %d 家可直达站内搜索)"
      % (os.path.getsize(os.path.join(OUT, "sites.json")) / 1024, len(sites_out), _direct))

# ---------- cat/<i>.json ----------
for idx, c in enumerate(cats):
    kw = c["keyword"]
    sl = spec_by_kw.get(kw, [])
    sl = sorted(sl, key=lambda s: (-s["n"], s["low"]["price"]))
    data = {
        "kw": kw,
        "group": c["group"],
        "mc": c["merchant_count"],
        "rows": [pack_row(r, kw) for r in c["rows"]],
        "specs": [{
            "sp": s["spec"],
            "n": s["n"],
            "lo": r2(s["low"]["price"]),
            "hi": r2(s["high"]["price"]),
            "sd": round(s["spread"], 1),
            "rows": [pack_row(r, s["kw"]) for r in s["rows"]],
        } for s in sl],
    }
    json.dump(data, open(os.path.join(CATDIR, "%d.json" % idx), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

# 报告体积
total = 0
for root, _, files in os.walk(OUT):
    for f in files:
        total += os.path.getsize(os.path.join(root, f))

# 统计有多少条记录拿到了商家官网商品页直链
_nrow = _nlink = 0
for idx, c in enumerate(cats):
    kw = c["keyword"]
    for s in spec_by_kw.get(kw, []):
        for r in s["rows"]:
            _nrow += 1
            if link_for(r["site_id"], s["kw"], r["name"], r["price"]):
                _nlink += 1

print("meta.json     %6.1f KB" % (os.path.getsize(os.path.join(OUT, "meta.json")) / 1024))
print("merchants     %6.1f KB" % (os.path.getsize(os.path.join(OUT, "merchants.json")) / 1024))
print("cat/*.json    %6.1f KB (%d 个)" % (total / 1024, len(cats)))
print("品类 %d | 规格 %d | 可比 %d | 条目 %d | 商家 %d"
      % (len(cats), len(specs), meta["stats"]["comp"], a["total_items"], len(merchants)))
print("商品直链覆盖 %d/%d = %.1f%%" % (_nlink, _nrow, 100.0 * _nlink / max(1, _nrow)))
