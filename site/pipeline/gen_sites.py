# -*- coding: utf-8 -*-
"""把 _probe 的探测结果固化成 site/pipeline/sites.json（构建输入）

输入:
  _probe/domains.json           站点 id -> {name, url}
  _probe/site_search_map.json   站点 id -> {base, search 模板, note}
  _probe/site_verify.json       站点 id -> {ok, ...}  实测是否真能搜出商品
输出:
  site/pipeline/sites.json      站点 id -> {name, base, search, verified, note}
规则:
  只有「实测能搜出商品」的模板才会保留 search；否则前端退化为跳官网首页，
  避免把用户送到一个空结果的搜索页。
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # kaquan/
PROBE = os.path.join(ROOT, "_probe")
OUT = os.path.join(HERE, "sites.json")

# 探针抓到的 URL 里常带一次性时间戳（防缓存参数），固化时必须去掉
DROP_PARAM = re.compile(r"[?&]t=\d+")


def clean(u):
    if not u:
        return u
    u = DROP_PARAM.sub("", u)
    return u.replace("?&", "?").rstrip("?&")


def load(name):
    p = os.path.join(PROBE, name)
    if not os.path.exists(p):
        print("缺少 %s" % name)
        return {}
    return json.load(open(p, encoding="utf-8"))


doms = load("domains.json")
smap = load("site_search_map.json")
ver = load("site_verify.json")
map2 = load("site_search_map2.json")     # probe3：列表页内搜索框实测得出的模板

out = {}
for sid, d in doms.items():
    s = dict(smap.get(sid) or {})
    v = ver.get(sid) or {}
    m2 = map2.get(sid) or {}
    # probe3 实测到的模板优先级最高（它是"页面内搜索框真实跳转"得出的）
    if m2.get("search"):
        s["search"] = clean(m2["search"])
        s["note"] = "probe3"
        verified = True
    else:
        verified = bool(v.get("ok"))
    base = (s.get("base") or d.get("url") or "").rstrip("/")
    if not base and m2.get("entry"):
        base = m2["entry"].replace(r"/(inside/goodsList|category).*$", "")
    search = clean(s.get("search")) if verified else None
    out[sid] = {
        "name": d.get("name") or s.get("name") or "",
        "base": base,
        "search": search,
        "verified": verified,
        "note": s.get("note") or "",
    }

json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

n_ok = sum(1 for x in out.values() if x["search"])
print("写入 %s" % OUT)
print("共 %d 家，其中 %d 家可直达站内搜索" % (len(out), n_ok))
for sid, x in sorted(out.items(), key=lambda kv: int(kv[0])):
    print("  %-4s %-18s %s %s" % (sid, x["name"][:18], "✅" if x["search"] else "  ",
                                  (x["search"] or x["base"])[:70]))
