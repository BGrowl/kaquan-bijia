# -*- coding: utf-8 -*-
"""商品名归一化：把同一件商品的不同写法合并（用于跨商家同款比价）"""
import re

BRACKET = re.compile(r"[【】\[\]（）()『』{}<>《》\"“”']")
SEP = re.compile(r"[丨|/\\~\-—_,，。.、:：;；!！?？*#@￥$%^&+=`'\s]+")

NOISE = re.compile(
    r"(自动充值|人工充值|人工快充|自动发货|官方直充|官方直冲|官方接口|官方CDK|官方兑换码|官方链接|"
    r"渠道链接|特价快充|特价|快充|秒单|秒充|直充|直冲|代充|代下单|接码|卡密|免码兑换|账号直充|"
    r"链接直冲|链接兑换|兑换卡密|自助点餐|自助提卡|链接|质保\d*小时|质保|无限制|有失败率|失败率|"
    r"请阅读商品详情|详情|一号一次|无资格自动退|自助撤单|联系客服|高价|特丨|特殊|不限制|现货|"
    r"下单前|下单后|支持|仅限|只支持|仅|官方|正规|稳定|24小时|全天|小时到|小时内到账|到账|"
    r"立即|当天|自助|新用户|首充|首单|卖家|店铺|商家|信誉|皇冠|金牌|认证|可用|通用|包售后|"
    r"正品|新品|热卖|爆款|低价|优惠|抢购|限时|全国|三端|手机|平板|电脑|端|使用|中途|不可更换设备|"
    r"兑换|平安|质保\d*[Hh]|\d+[Hh]|\d+小时|\d+分钟|分钟|秒到|秒杀|担保|售后)")

# 商品名前缀（商家自己的分区/编号）
PREFIX = re.compile(r"^([A-Za-z]?\d{0,2}区|[A-Za-z]{1,2}\d{0,2}|特价区|新品区|混区|餐饮混区|[A-Z]{1,2})+")

SIZE = [(re.compile(r"(超大杯|大杯|中杯|小杯)"), lambda m: m.group(1))]

# 面额/数量: 5元 / 50元 / 10个 / 1GB
AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(GB|G|MB|M|元|个|张|份|币|钻|点|天|个月|月|年)")
NUMCN = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4", "五": "5", "六": "6",
         "七": "7", "八": "8", "九": "9", "十": "10"}


def norm(name):
    s = str(name or "")
    s = BRACKET.sub(" ", s)
    s = NOISE.sub(" ", s)
    s = PREFIX.sub(" ", s)
    s = SEP.sub("", s)
    s = re.sub(r"^\d+区", "", s)
    return s.strip()


if __name__ == "__main__":
    import json
    import collections
    import sys
    D = json.load(open("data/kw_%s.json" % sys.argv[1], encoding="utf-8"))
    g = collections.defaultdict(list)
    for x in D["items"]:
        g[norm(x["name"])].append(x)
    multi = {k: v for k, v in g.items() if len(set(z["site_id"] for z in v)) >= 2}
    print("原始条目 %d -> 归并后规格 %d，其中 ≥2 家在售 %d"
          % (len(D["items"]), len(g), len(multi)))
    print("\n--- ≥2 家在售的规格（按最低价） ---")
    for k, v in sorted(multi.items(), key=lambda kv: min(z["price"] for z in kv[1]))[:35]:
        p = min(z["price"] for z in v)
        n = len(set(z["site_id"] for z in v))
        print("%8.2f  %2d家  %s" % (p, n, k[:58]))
    print("\n--- 只剩 1 家的长尾样例 ---")
    one = [k for k, v in g.items() if len(set(z["site_id"] for z in v)) == 1]
    for k in one[:10]:
        print("        ", k[:60])
