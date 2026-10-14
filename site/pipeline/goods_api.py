# -*- coding: utf-8 -*-
"""商家站商品接口适配层（卡易信 / 卡速售）

目的：把「聚合站的一条商品记录」对应到「商家官网的商品详情/下单页」。
两套系统都实测可以匿名调用：

  卡易信(卡易信站点形如 /inside/goodsList?keyWord=)
      POST {base}/inside/getGoods
      body: brandId=&dirId=&keyWord=<kw>&dataType=&isp=&nowPage=<n>&goodType=
            &orderType=&saleState=&minPrice=&maxPrice=&showStock=1&EveryPage=100
      返回 cutPage.AllPage / goodsList[{Gid, Name, StockPrice, One, Two, Three}]
      商品页: {base}/inside/buyGoods?goodId=<Gid>

  卡速售(站点形如 /category?keyword=)
      GET {base}/front/goods/goods_list?sort_type=1&sort=&page=<n>&limit=100
          &keyword=<kw>&pcategory_id=&category_id=&gcategory_id=
      需要请求头 Sign = md5(md5(md5(SALT)+ts)) + ts   （ts = unix 秒）
      返回 data.total / data.list[{id, goods_name, goods_price, min_level_price}]
      商品页: {base}/goods?id=<id>
"""
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 卡速售站点签名密钥（从其前端 app.js 的 5f87 模块中提取）
KS_SALT = "front18a3257675b85febdfcdd83e7150c0b9"

EVERY_PAGE = 100          # 卡易信每页条数（接口支持自定义）
KS_LIMIT = 100            # 卡速售每页条数
MAX_PAGE = 6              # 单个关键词最多翻页数（600 条，足够覆盖匹配所需）

TIMEOUT = 30
RETRY = 3


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def ks_sign():
    """卡速售签名：md5(md5(md5(SALT)+ts)) + ts"""
    t = str(int(round(time.time())))
    o = _md5(KS_SALT)
    inner = _md5(o + t)
    return _md5(inner) + t


def _open(req, retry=RETRY):
    last = None
    for i in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(0.6 * (i + 1))
    raise last


def _post(url, data, referer):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
         "Accept-Language": "zh-CN,zh;q=0.9", "Referer": referer,
         "X-Requested-With": "XMLHttpRequest",
         "Content-Type": "application/x-www-form-urlencoded"}
    body = urllib.parse.urlencode(data).encode()
    return _open(urllib.request.Request(url, data=body, headers=h))


def _get(url, referer, extra=None):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
         "Accept-Language": "zh-CN,zh;q=0.9", "Referer": referer}
    if extra:
        h.update(extra)
    return _open(urllib.request.Request(url, headers=h))


# ---------------- 卡易信 ----------------

def fetch_yixin(base, kw):
    """返回 [{id, name, price, url}]"""
    out = []
    page = 1
    while page <= MAX_PAGE:
        ref = "%s/inside/goodsList?keyWord=%s" % (base, urllib.parse.quote(kw))
        t = _post(base + "/inside/getGoods", {
            "brandId": "", "dirId": "", "keyWord": kw, "dataType": "", "isp": "",
            "nowPage": page, "goodType": "", "orderType": "", "saleState": "",
            "minPrice": "", "maxPrice": "", "showStock": 1,
            "EveryPage": EVERY_PAGE,
        }, ref)
        d = json.loads(t)
        gl = d.get("goodsList") or []
        for g in gl:
            gid = g.get("Gid")
            if gid is None:
                continue
            price = None
            for k in ("StockPrice", "One", "Two", "Three"):
                try:
                    if g.get(k) not in (None, "", 0):
                        price = float(g[k])
                        break
                except (TypeError, ValueError):
                    pass
            out.append({
                "id": gid,
                "name": (g.get("Name") or "").strip(),
                "price": price,
                "url": "%s/inside/buyGoods?goodId=%s" % (base, gid),
            })
        cp = d.get("cutPage") or {}
        allpage = int(cp.get("AllPage") or 0)
        if not gl or page >= allpage:
            break
        page += 1
        time.sleep(0.25)
    return out


# ---------------- 卡速售 ----------------

def fetch_susou(base, kw):
    out = []
    page = 1
    while page <= MAX_PAGE:
        ref = "%s/category?keyword=%s" % (base, urllib.parse.quote(kw))
        u = ("%s/front/goods/goods_list?sort_type=1&sort=&page=%d&limit=%d"
             "&keyword=%s&pcategory_id=&category_id=&gcategory_id="
             % (base, page, KS_LIMIT, urllib.parse.quote(kw)))
        t = _get(u, ref, {"Sign": ks_sign()})
        d = json.loads(t)
        if d.get("code") != 200:
            raise RuntimeError("卡速售返回 %s" % d.get("msg"))
        data = d.get("data") or {}
        lst = data.get("list") or []
        total = int(data.get("total") or 0)
        for g in lst:
            gid = g.get("id")
            if gid is None:
                continue
            price = None
            for k in ("min_level_price", "goods_price", "can_price"):
                try:
                    v = float(g.get(k))
                    if v > 0:
                        price = v
                        break
                except (TypeError, ValueError):
                    pass
            out.append({
                "id": gid,
                "name": (g.get("goods_name") or "").strip(),
                "price": price,
                "url": "%s/goods?id=%s" % (base, gid),
            })
        if not lst or len(out) >= total:
            break
        page += 1
        time.sleep(0.25)
    return out


# ---------------- 匹配 ----------------

_PUNC = re.compile(r"[\s\u3000()（）\[\]【】{}<>《》|·,，.。:：;；'\"“”‘’!！?？~～\-—_/\\+*&#@$%^=&]+")


def norm_name(s):
    """商品名归一：去空白与标点、统一大小写，便于跨站比对"""
    s = (s or "").lower()
    s = _PUNC.sub("", s)
    return s


def build_index(products):
    """商品列表 -> {归一化名: [{url, price}]}"""
    idx = {}
    for p in products:
        k = norm_name(p["name"])
        if not k:
            continue
        idx.setdefault(k, []).append({"url": p["url"], "price": p["price"]})
    return idx


def pick(idx, name, price=None, tol=0.05):
    """按名字取链接；同名多条时用价格挑最接近的"""
    cands = idx.get(norm_name(name))
    if not cands:
        return None
    if len(cands) == 1 or price is None:
        return cands[0]["url"]
    best, bd = None, None
    for c in cands:
        if c["price"] is None:
            continue
        d = abs(c["price"] - float(price))
        if bd is None or d < bd:
            best, bd = c, d
    if best is not None and bd is not None and bd <= max(tol, float(price) * 0.02 + 0.01):
        return best["url"]
    return cands[0]["url"]


SYSTEMS = {
    "卡易信": fetch_yixin,
    "卡速售": fetch_susou,
}


def fetch_products(system, base, kw):
    f = SYSTEMS.get(system)
    if not f:
        raise RuntimeError("未知系统 %s" % system)
    return f(base.rstrip("/"), kw)
