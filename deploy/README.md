# 卡券比价雷达 · 自托管部署包

把「卡券集市全站比价」整站搬到**你自己的服务器 + 你自己的域名**下运行，不再使用任何平台的域名。

包含能力：

- 前端站点（原生 JS，无框架）+ 零依赖 Python 后端（只用标准库，**不需要 pip install 任何东西**）
- **定时自动重抓** kaquanjishi.com 的批量查价数据（默认每 40 分钟一轮），并自动重算、覆盖站点数据
- 手动刷新接口 `/api/refresh`、状态接口 `/api/status`
- 首启自带**热启动数据**（约 3MB 原始抓取缓存），所以一部署上去站点就是完整的，不用等第一轮抓完

---

## 一、准备条件

| 项目 | 要求 |
|---|---|
| 服务器 | 一台 Linux（x86_64 / arm64 均可），公网可访问，**有外网出口**（能访问 kaquanjishi.com） |
| 域名 | 你自己的一个域名（如 `kaquan.example.com`），可加 A 记录 |
| 运行环境 | **Docker**（方式 A，推荐）或 **Python 3.8+**（方式 B） |
| 端口 | 80 / 443 对外，容器内部 8000，映射到本机 18801 |

> 说明：本服务**不需要**数据库、Redis 之类的外部依赖；数据就是一个 JSON 文件和一批缓存文件，全部落在 `cache/` 目录里。

---

## 二、上传与解压

```bash
# 在本地把 kaquan-selfhost.tar.gz 传到服务器（示例）
scp kaquan-selfhost.tar.gz root@你的服务器IP:/opt/

# 登录服务器后解压
cd /opt
tar -xzf kaquan-selfhost.tar.gz
cd kaquan-selfhost
ls        # 应看到 app/ Dockerfile entrypoint.sh docker-compose.yml Caddyfile nginx.conf README.md
```

域名解析：到你的 DNS 服务商，给 `kaquan.example.com`（换成你的）添加一条 **A 记录**指向服务器公网 IP。
DNS 生效一般几分钟。

---

## 三、方式 A：Docker 部署（推荐，最省事）

```bash
cd /opt/kaquan-selfhost

# 可选：自定义配置
cp .env.example .env
vi .env          # 想改刷新间隔就改 REFRESH_MINUTES

# 构建并启动
docker compose up -d --build

# 看日志：应出现「首次启动：导入热启动数据」→「服务已启动」
docker compose logs -f --tail=50
```

启动后服务只监听本机 `127.0.0.1:18801`，**必须再接一层反向代理**（下一步）才能用域名访问。

验证一下：

```bash
curl -s http://127.0.0.1:18801/api/status
# 期望：{"version":1,"updated":"...","running":false,...,"nextIn":2350}
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18801/     # 200
```

---

## 四、方式 B：裸机部署（不想用 Docker）

```bash
# 1) 建用户并放代码
sudo useradd -r -m -s /usr/sbin/nologin kaquan || true
sudo mkdir -p /opt/kaquan
sudo cp -R /opt/kaquan-selfhost/app/. /opt/kaquan/
# 首启热启动数据：包里自带的 seed 拷进可写缓存目录（注意源路径是 /opt/kaquan/cache-seed）
sudo mkdir -p /opt/kaquan/cache
sudo cp -R /opt/kaquan/cache-seed/. /opt/kaquan/cache/
sudo chown -R kaquan:kaquan /opt/kaquan
sudo rm -rf /opt/kaquan/cache-seed        # 已导入，可删

# 2) 装 systemd 服务
sudo cp /opt/kaquan-selfhost/kaquan.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kaquan
sudo systemctl status kaquan --no-pager
```

> `kaquan.service` 里默认 `HOST=127.0.0.1 PORT=18801`，由 Nginx/Caddy 反代。
> 如果你的 Python 不在 `/usr/bin/python3`，改一下 `ExecStart`。

---

## 五、接上你的域名 + HTTPS

### 方案 1：Caddy（最省事，自动申请并自动续期证书）

```bash
# 安装 Caddy 后
sudo cp /opt/kaquan-selfhost/Caddyfile /etc/caddy/Caddyfile
sudo vi /etc/caddy/Caddyfile        # 把 kaquan.example.com 换成你的域名
sudo systemctl reload caddy
```

Caddy 会自动向 Let's Encrypt 申请证书。前提：域名已解析到本机、且 80/443 已放通。

### 方案 2：Nginx（你已有 Nginx + certbot）

```bash
sudo cp /opt/kaquan-selfhost/nginx.conf /etc/nginx/conf.d/kaquan.conf
sudo vi /etc/nginx/conf.d/kaquan.conf     # 全局替换成你的域名
# 先注释掉 443 那个 server 块，跑通 80 端口后签发证书：
sudo certbot --nginx -d kaquan.example.com
sudo nginx -t && sudo systemctl reload nginx
```

完成后访问 `https://kaquan.example.com` 即为你的站点。

---

## 六、验证清单

```bash
curl -s -o /dev/null -w "首页 %{http_code}\n"      https://你的域名/
curl -s -o /dev/null -w "数据 %{http_code}\n"      https://你的域名/data/meta.json
curl -s                                            https://你的域名/api/status
```

页面右上角应显示「数据更新 <时间>」和一个**绿色脉冲点**（自动更新已开启）；正在抓取时会变成橙色并显示 `正在更新 7/79 …` 的进度。

手动催一次刷新：

```bash
curl -X POST https://你的域名/api/refresh
# 然后看状态：running 变 true，progress 显示进度
curl -s https://你的域名/api/status
```

---

## 七、日常运维

| 需求 | 做法 |
|---|---|
| 看日志 | Docker：`docker compose logs -f`　裸机：`journalctl -u kaquan -f` |
| 改刷新间隔 | 改 `REFRESH_MINUTES`（Docker 改 `.env` 后 `docker compose up -d`；裸机改 unit 后 `systemctl daemon-reload && systemctl restart kaquan`） |
| 手动刷数据 | `curl -X POST https://你的域名/api/refresh` |
| 备份 | 备份持久化卷/`cache/` 目录即可（Docker：`docker run --rm -v kaquan-cache:/d -v $PWD:/b alpine tar czf /b/cache.tgz -C /d .`） |
| 更新代码 | 重新打包上传后 `docker compose up -d --build`；`cache/` 卷不动，数据不丢 |

**环境变量**

| 变量 | 默认 | 作用 |
|---|---|---|
| `PORT` | 8000（容器内） | 服务监听端口 |
| `HOST_PORT` | 18801 | 映射到**本机回环**的端口（改这个要同步改 Caddy/Nginx 里的反代地址） |
| `HOST` | `0.0.0.0`（Docker）/ `127.0.0.1`（unit） | 绑定地址 |
| `REFRESH_MINUTES` | 40 | 自动重抓间隔，**不建议低于 30**（源站有频控） |
| `STALE_MINUTES` | 20 | 数据超过该时长时，用户访问会补刷一次 |

> Docker 方式下这些变量写在 `.env` 里即可（`docker-compose.yml` 已用 `${VAR:-默认值}` 引用）；
> 裸机方式下写在 `kaquan.service` 的 `Environment=` 行里。

---

## 八、排错

| 现象 | 原因 / 处理 |
|---|---|
| 页面打开但一直「数据载入失败」 | 用的是 `file://` 或静态托管，读不到 `/data/*.json`。必须由这个后端服务提供 |
| 状态一直显示「正在更新」很久 | 正常。一轮要抓 79 个关键词，约 12~16 分钟；日志里看到 `RATE ... 限流，等待 Ns` 说明在自我退避，属预期 |
| 状态显示「上次更新未成功」 | 看日志里最后一条 `FAIL`。若只是个别品类失败，站点会沿用上一轮数据，不影响使用 |
| 显示「本轮数据不完整，已保留上一版」 | 该轮成功的关键词不足一半，程序主动放弃覆盖，**这是保护机制**，不是故障 |
| 抓取大面积失败、日志满是 `查询过于频繁` | 源站频控。把 `REFRESH_MINUTES` 调大到 60~120，或稍后再试；程序本身已带退避重试 |
| 容器重启后数据「回到初始」 | 持久化卷没挂上。确认 `docker-compose.yml` 里 `kaquan-cache:/app/cache` 存在 |
| 域名访问 502 | 反代没连上后端。确认 `curl http://127.0.0.1:18801/api/status` 本机可通 |

---

## 九、目录结构

```
kaquan-selfhost/
├── app/                    应用本体（拷到服务器后就是运行目录）
│   ├── server.py           静态服务 + /api/status + /api/refresh + 后台定时抓取
│   ├── index.html          前端页面
│   ├── assets/             style.css / app.js（原生 JS）
│   ├── data/               站点数据：meta.json / merchants.json / cat/<i>.json
│   ├── pipeline/           fetch.py（抓取）/ analyze.py（清洗比价）/ build_web.py（出站点数据）/ keywords.json
│   └── cache-seed/work/    热启动原始数据（首启导入到 cache/）
├── Dockerfile / docker-compose.yml / entrypoint.sh
├── Caddyfile / nginx.conf   两种反代样例
├── kaquan.service           裸机 systemd unit
├── .env.example
└── README.md
```

数据来源：`kaquanjishi.com` 的批量查价接口。价格是抓取时刻的快照，实时会变，下单前请以商家页面为准。

> ⚠️ 版权与合规：本包仅为比价工具，抓取的是公开报价接口。请自行控制抓取频率（默认 40 分钟一轮已经比较克制），不要改小到高频轮询。
