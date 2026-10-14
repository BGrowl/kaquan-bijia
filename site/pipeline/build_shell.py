# -*- coding: utf-8 -*-
"""
把静态壳 (index.html + style.css + app.js) 与首屏数据 (meta/merchants/sites)
内联打包成「单请求自包含首页」 -> public/index.html

为什么这么做（性能诊断结论）：
  改造前首屏要发 6 个请求，且被一个注定 404 的 /api/status 串行阻塞 ——
  实测该请求耗时约 1.0s、还要下载 8KB surge 404 页面，排在所有数据加载之前。
  叠加 surge 全站 cache-control: max-age=0, must-revalidate（等于完全不缓存），
  每个资源都要重新回源，手机端首屏轻松 5~15 秒（用户反馈"半天加载不出来"）。

  内联后首屏只剩 1 个 HTML 请求（gzip 约 18KB），品类详情分片 data/cat/<i>.json
  仍在用户点进详情时按需加载，不进首屏。

用法： KAQUAN_DATA=<public/data> python build_shell.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.normpath(os.path.join(HERE, ".."))

DATA = os.environ.get("KAQUAN_DATA") or os.path.join(SITE, "..", "public", "data")
PUB = os.path.normpath(os.path.join(DATA, ".."))

SHELL = os.path.join(SITE, "index.html")
CSS = os.path.join(SITE, "assets", "style.css")
JS = os.path.join(SITE, "assets", "app.js")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def load_json(p):
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def js_json(obj):
    """序列化成可安全放进 <script> 的 JSON（转义 </ 防止提前闭合脚本）"""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</", "<\\/")


def main():
    html = read(SHELL)
    css = read(CSS)
    js = read(JS)

    meta = load_json(os.path.join(DATA, "meta.json"))
    merchants = load_json(os.path.join(DATA, "merchants.json")) or []
    sites = load_json(os.path.join(DATA, "sites.json")) or {}
    if not meta:
        print("build_shell: 缺少 data/meta.json，跳过内联", file=sys.stderr)
        return 1

    boot = js_json({"meta": meta, "merchants": merchants, "sites": sites})
    css_safe = css.replace("</style>", "<\\/style>")
    js_safe = js.replace("</script>", "<\\/script>")

    # 1) 外链样式 -> 内联
    #    注意：replacement 必须用 lambda 返回。直接传字符串会被 re 当成模板，
    #    JS/CSS 里的 \d \s 等转义会触发 "bad escape" 而报错。
    html, n1 = re.subn(r'<link rel="stylesheet" href="assets/style\.css">',
                       lambda m: "<style>\n" + css_safe + "\n</style>", html)
    # 2) 外链脚本 -> 首屏数据 + 内联脚本
    html, n2 = re.subn(r'<script src="assets/app\.js"></script>',
                       lambda m: ("<script>window.__BOOT__=" + boot + ";</script>\n"
                                  "<script>\n" + js_safe + "\n</script>"), html)

    if not (n1 and n2):
        print("build_shell: 没能在 index.html 里定位到外链标签"
              "(style=%d script=%d)，已中止，避免发布出半成品" % (n1, n2),
              file=sys.stderr)
        return 1

    out = os.path.join(PUB, "index.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)

    raw = os.path.getsize(out)
    print("index.html    %6.1f KB 内联单文件（css %.1f + js %.1f + 数据 %.1f）"
          % (raw / 1024.0, len(css) / 1024.0, len(js) / 1024.0, len(boot) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
