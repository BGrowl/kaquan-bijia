# -*- coding: utf-8 -*-
"""
卡券集市 全站比价分析
产出:
  1) 每个品类 -> 各商家最低价(即"每家里面相同品类最便宜的一个")
  2) 同规格 -> 跨商家比价(找出全网最低)
"""
import csv
import json
import os
import re
from collections import defaultdict

from norm import norm as norm_product

HERE = os.path.dirname(os.path.abspath(__file__))
# 原始抓取数据目录 & 输出目录（网站版由 server.py 通过环境变量注入）
DATA = os.environ.get("KAQUAN_WORK") or os.path.join(HERE, "work")
OUT = DATA
os.makedirs(DATA, exist_ok=True)

# ---------- 垃圾商品过滤 ----------
# 1) 教程/课程/项目/引流等非卡券商品
# 2) 刷量类: 刷播放量/人气/粉丝/点赞/挂机 等非实物权益
# 3) 说明页/公告页: "商品说明""下单必看"这类不是商品
JUNK = re.compile(
    r"(教程|课程|教学|培训|实操|干货|资料|素材|源码|软件|脚本|破解|项目|玩法|变现|副业|"
    r"月入|日入|周入|引流|涨粉|网赚|赚钱|盈利|分成计划|攻略|代运营|咨询|方案|白皮书|"
    r"学习|视频课|全套|合集|工具包|模板|解压密码|加密视频|网盘拉新|拉新|地推|"
    r"秘籍|秘籍|破局|黑标|风口|红利|手册|SOP|小白|零基础|速成|运营策略|带货|躺赚|私域|引爆|"
    r"实战营|训练营|特殊名|空白|居中名|歌曲收藏|收藏|爱心|点在追|在看|战力|代查|看说明|看详情|"
    r"不售后|超时不售后|曝光|进店|点击量|PV|UV|拇指|赞|双击|"
    r"播放量|视频播放|播放|刷量|刷单|代刷|秒刷|刷粉|人气|直播间人气|热度|同涨|涨热度|"
    r"弹幕|访客|大拇指|互动量|观看量|围绕|评论|"
    r"粉丝|点赞|关注量|浏览量|挂机|助力|代练|陪玩|代打|上分|亲密度|火花|"
    r"商品说明|下单必看|必看|购买须知|须知|注意事项|拍前|售后说明|测试商品|测试专用|"
    r"撒钱|一单|必赚|复制粘贴|薅|羊毛|佣金|返利|提现|返现|悬赏|兼职|招募|招人|加群|进群|"
    r"看广告|做任务|注册送|免费领|秒赚|日赚|试玩|下载APP|下载app|"
    r"课|技术|搬运|破戒|破解|免安装|硬盘版|豪华版|完整版|官方中文|绿色版|未加密|集成|"
    r"回放|完播|集卡|福利商品|噱头|实战|矩阵|起量|托管|蓝海|跨境|精髓|最高省|特惠下单|秒单|"
    r"改战区|真人关注|歌手关注|被盗|异地登录|捏脸|下载」|"
    r"弟子班|测款|放量|出单|SKU|切车|调优|掘金|爆单|门槛|成本启动|闲鱼|保姆级|手把手|带你|"
    r"超详细|揭秘|解密|免费分享|可无限扩大|可测|稳定日|掌握|学会|Adobe|大师版|全家桶|中文版|"
    r"礼金版|不必中|抽奖|盲盒|全指南|开店|注册|指南|转换工具|战区|积分兑换|"
    r"入门|方法论|无货源|起盘|技巧|解锁|纯净|无广告|名片|DIY|自定义|资源|"
    r"关注|优惠券包|红包封面|表情包|壁纸|头像|"
    r"专区-|说明页|公告|请勿拍|勿拍|勿下单|占位|示例)"
)
# ---------- 营销/发货方式噪声词(不构成不同商品) ----------
NOISE = re.compile(
    r"(自动充值|人工充值|人工快充|自动发货|官方直充|官方直冲|官方接口|官方CDK|官方兑换码|"
    r"特价快充|特价|快充|秒单|秒充|直充|直冲|代充|代下单|接码|卡密|免码兑换|账号直充|"
    r"链接直冲|链接兑换|质保\d*小时|质保|无限制|有失败率|失败率|请阅读商品详情|详情|"
    r"一号一次|无资格自动退|自助撤单|联系客服|高价|特价|特丨|特殊|不限制|现货|"
    r"下单前|下单后|支持|仅限|只支持|仅|官方|正规|稳定|24小时|全天|小时到|小时内到账|"
    r"到账|立即|当天|自助|新用户|首充|首单|卖家|店铺|商家|信誉|皇冠|金牌|认证)")
BRACKET = re.compile(r"[【】\[\]（）()『』{}<>《》\"“”']")
SEP = re.compile(r"[丨|/\\~\-—_,，。.、:：;；!！?？*#@￥$%^&+=`'\s]+")

# 时长归一化(顺序敏感)
DUR_MAP = [
    (re.compile(r"(年卡|包年|年度|12个月|十二个月|1年|一年|365天|半年卡|6个月|六个月)"), "年卡/半年"),
    (re.compile(r"(季卡|季度|3个月|三个月|90天)"), "季卡"),
    (re.compile(r"(月卡|包月|1个月|一个月|30天|31天|28天)"), "月卡"),
    (re.compile(r"(半月卡|半个月|15天|14天)"), "半月卡"),
    (re.compile(r"(周卡|包周|7天|一周|1周|一星期)"), "周卡"),
    (re.compile(r"(天卡|日卡|1天|一天|24小时|1日|三日|3天|5天)"), "天卡"),
]
TIER = re.compile(r"(豪华绿钻|绿钻|黑胶|音乐包|听书|黄金|白金|铂金|星钻|钻石|至尊|联合会员|联名|"
                  r"标准|SVIP|VIP|超级|大会员|正式)")


def clean_name(name):
    s = BRACKET.sub(" ", str(name or ""))
    s = NOISE.sub(" ", s)
    s = SEP.sub(" ", s)
    return re.sub(r"\s+", "", s).strip()


def duration_of(name):
    s = str(name or "")
    for pat, tag in DUR_MAP:
        if pat.search(s):
            return tag
    return ""


def tier_of(name):
    m = TIER.search(clean_name(str(name or "")))
    return m.group(1) if m else ""


MEMBER_KW = {"爱奇艺", "腾讯视频", "优酷", "芒果TV", "哔哩哔哩", "网易云音乐", "QQ音乐", "百度网盘"}
FACE_KW = {"京东E卡", "天猫超市", "话费", "Q币", "流量"}
MEMBER_HINT = re.compile(r"(会员|VIP|svip|SVIP|黄金|白金|星钻|钻石|超级|大会员|音乐包|绿钻|黑胶)")
# 会员类品类只保留真正的会员/卡券商品，滤掉刷量、红包、游戏名等
MEMBER_ONLY = re.compile(r"(会员|VIP|svip|SVIP|黄金|白金|星钻|钻石|至尊|超级|大会员|绿钻|黑胶|音乐包|卡)")
FACE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(GB|G|MB|M|元|个)")


def spec_key(kw, name):
    """同款商品键：
       - 会员类品类：品牌 + 会员等级 + 时长（把 7天/周卡 这类写法统一）
       - 其它品类：通用归一化后的商品名（保留面额、杯型、口味等规格差异）
    """
    s = str(name or "")
    if kw in MEMBER_KW:
        d = duration_of(s)
        if d:
            return "%s · %s · %s" % (kw, tier_of(s) or "标准", d)
    return norm_product(s) or None


def spec_tag(name):
    """交付方式标签，帮用户区分直充/卡密/共享号"""
    s = str(name or "")
    if re.search(r"(共享|合租|租号|共用)", s):
        return "共享号"
    if re.search(r"(卡密|CDK|兑换码|免码|卡号|链接兑换)", s):
        return "卡密/兑换码"
    if re.search(r"(代下单|代下|代购|代付)", s):
        return "代下单"
    if re.search(r"(直充|直冲|自动充值|接口|秒单|官方充值)", s):
        return "直充"
    return "其他"


def load_all():
    recs = []
    groups = {}
    for fn in sorted(os.listdir(DATA)):
        if not fn.startswith("kw_") or not fn.endswith(".json"):
            continue
        blob = json.load(open(os.path.join(DATA, fn), encoding="utf-8"))
        kw = blob["keyword"]
        for it in blob.get("items", []):
            name = (it.get("name") or "").strip()
            if not name:
                continue
            if JUNK.search(name):
                continue
            if kw in MEMBER_KW and not MEMBER_ONLY.search(name):
                continue
            if kw in ("话费", "流量") and "会员" in name:
                continue
            if kw == "流量" and not re.search(r"(流量包|话费|充值|元|G|GB)", name):
                continue
            price = float(it.get("price") or 0)
            # 卡券单价上限 5000 元；超出多为商家标错的占位价
            if price <= 0 or price > 5000:
                continue
            recs.append({
                "kw": kw,
                "name": name,
                "price": price,
                "site_id": it.get("site_id"),
                "site_name": it.get("site_name") or "",
                "system": it.get("system_name") or "",
                "tag": spec_tag(name),
                "spec": spec_key(kw, name),
            })
    return recs


def build(recs, keywords_meta):
    # 品类 -> 商家 -> 最低价商品
    per_cat = defaultdict(dict)
    for r in recs:
        k = (r["kw"], r["site_id"])
        cur = per_cat[r["kw"]].get(r["site_id"])
        if cur is None or r["price"] < cur["price"]:
            per_cat[r["kw"]][r["site_id"]] = r

    cats = []
    for kw, g in per_cat.items():
        rows = sorted(g.values(), key=lambda x: x["price"])
        cats.append({
            "keyword": kw,
            "group": keywords_meta.get(kw, {}).get("group", ""),
            "merchant_count": len(rows),
            "cheapest": rows[0] if rows else None,
            "rows": rows,
        })
    cats.sort(key=lambda c: (c["group"], -c["merchant_count"]))

    # 商品规格 -> 商家 -> 最低价（覆盖全部品类）
    per_spec = defaultdict(dict)
    for r in recs:
        if not r["spec"]:
            continue
        cur = per_spec[r["spec"]].get(r["site_id"])
        if cur is None or r["price"] < cur["price"]:
            per_spec[r["spec"]][r["site_id"]] = r

    grp_of = keywords_meta
    specs = []
    for sp, g in per_spec.items():
        rows = sorted(g.values(), key=lambda x: x["price"])
        med = rows[len(rows) // 2]["price"]
        # 剔除离群报价(高于中位数 3 倍或低于 1/3)，避免假"最低价"
        trimmed = [r for r in rows if med / 3 <= r["price"] <= med * 3]
        if len(trimmed) >= 2:
            rows = trimmed
        spread = (rows[-1]["price"] - rows[0]["price"]) / rows[-1]["price"] * 100 if rows[-1]["price"] else 0
        kw = sp.split(" · ")[0] if " · " in sp else rows[0]["kw"]
        specs.append({
            "spec": sp,
            "kw": rows[0]["kw"] if kw not in grp_of else kw,
            "group": grp_of.get(rows[0]["kw"], {}).get("group", ""),
            "n": len(rows),
            "low": rows[0],
            "high": rows[-1],
            "spread": spread,
            "rows": rows,
        })
    # 默认排序：先在售家数多的（可比性强），再按价格
    specs.sort(key=lambda s: (-s["n"], s["kw"], s["low"]["price"]))

    # 商家榜: 品类冠军 + 规格冠军
    mstat = defaultdict(lambda: {"name": "", "wins": 0, "cats": [], "appear": 0,
                                 "top3": 0, "spec_wins": 0})
    for c in cats:
        for i, r in enumerate(c["rows"]):
            s = mstat[r["site_id"]]
            s["name"] = r["site_name"]
            s["appear"] += 1
            if i < 3:
                s["top3"] += 1
            if r["price"] <= c["cheapest"]["price"] * 1.000001:
                s["wins"] += 1
                s["cats"].append(c["keyword"])
    # 规格级冠军: 在 ≥2 家在售的规格里报价最低
    for sp in specs:
        if sp["n"] < 2:
            continue
        lo = sp["low"]["price"]
        for r in sp["rows"]:
            if r["price"] <= lo * 1.000001:
                mstat[r["site_id"]]["spec_wins"] += 1
    merchants = [dict(id=k, **v) for k, v in mstat.items()]
    merchants.sort(key=lambda x: (-x["wins"], -x["spec_wins"], -x["top3"], x["name"]))

    return cats, specs, merchants


def main():
    kws = json.load(open(os.path.join(HERE, "keywords.json"), encoding="utf-8"))
    meta = {k["kw"]: k for k in kws}
    recs = load_all()
    cats, specs, merchants = build(recs, meta)
    json.dump({"cats": cats, "specs": specs, "merchants": merchants, "total_items": len(recs)},
              open(os.path.join(DATA, "analysis.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("有效商品条目:", len(recs), " 品类:", len(cats),
          " 商品规格:", len(specs), "(其中≥2家可比 %d)" % sum(1 for s in specs if s["n"] >= 2))
    print("--- 商家榜(品类最低价冠军数) ---")
    for m in merchants[:10]:
        print("  %-12s 冠军%2d  前3%2d  覆盖%2d  %s"
              % (m["name"], m["wins"], m["top3"], m["appear"], "/".join(m["cats"][:8])))
    print("--- 商品规格 TOP(在售家数) ---")
    for s in specs[:12]:
        print("  %-30s %2d家 ¥%.2f(%s) ~ ¥%.2f 差%.0f%%"
              % (s["spec"][:30], s["n"], s["low"]["price"], s["low"]["site_name"],
                 s["high"]["price"], s["spread"]))


if __name__ == "__main__":
    main()
