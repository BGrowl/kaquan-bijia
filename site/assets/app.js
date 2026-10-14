/* 卡券集市 · 全站比价 (纯原生 JS, 无依赖) */
(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var app = $('#app');

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function money(n) { return Number(n).toFixed(2); }
  function dv(t) {
    t = t || '其他';
    return '<span class="dv dv-' + esc(t.replace(/\//g, '')) + '">' + esc(t) + '</span>';
  }

  /* ---- 下单链接 ----
     优先级：商家官网的「商品详情/下单页」(r.u) > 官网站内搜索结果 > 官网首页
     kw 传该品类的品牌关键词（实测：用品牌名搜命中率最高，完整商品名几乎搜不到） */
  function merchantHref(id, kw) {
    var s = S.sites && S.sites[id];
    if (s && s.q && kw) {
      try { return s.q.replace('{kw}', encodeURIComponent(kw)); } catch (e) { }
    }
    if (s && s.b) return s.b;
    return (S.meta.siteBase || '') + id;
  }
  function merchantDirect(id) {
    var s = S.sites && S.sites[id];
    return !!(s && s.q && s.v);
  }
  function rowHref(r, kw) {
    return r.u || merchantHref(r.i, kw);
  }
  function rowLabel(r) {
    if (r.u) return '去下单 ›';
    return merchantDirect(r.i) ? '搜同款 ›' : '官网 ›';
  }
  function rowClass(r) {
    return r.u ? 'go buy' : (merchantDirect(r.i) ? 'go direct' : 'go');
  }
  function goLink(r, kw, txt) {
    return '<a class="' + rowClass(r) + '" href="' + esc(rowHref(r, kw)) +
      '" target="_blank" rel="noopener nofollow">' + (txt || rowLabel(r)) + '</a>';
  }

  var S = { meta: null, merchants: null, sites: {}, cache: {} };
  var F = { q: '', group: '', sort: 'price' };   // 首页筛选
  var G = { sort: 'n', q: '', all: false };      // 规格区筛选

  /* ================= 路由 ================= */
  function route() {
    var h = location.hash.replace(/^#\/?/, '');
    var tabs = document.querySelectorAll('#tabs a');
    for (var i = 0; i < tabs.length; i++) {
      var v = tabs[i].getAttribute('data-v');
      var on = (v === 'home' && !/^(c\/|m$|about$)/.test(h)) ||
               (v === 'merch' && h === 'm') || (v === 'about' && h === 'about');
      tabs[i].className = on ? 'on' : '';
    }
    window.scrollTo(0, 0);
    if (/^c\/\d+$/.test(h)) return loadCat(+h.slice(2));
    if (h === 'm') return renderMerch();
    if (h === 'about') return renderAbout();
    return renderHome();
  }

  /* ================= 首页 ================= */
  function renderHome() {
    if (!$('#grid')) buildShell();
    updateGrid();
  }

  function buildShell() {
    var m = S.meta;
    var h = '';
    h += '<div class="stats">' +
      '<div class="stat"><b>' + m.stats.cats + '</b><span>个品类</span></div>' +
      '<div class="stat"><b>' + m.stats.comp.toLocaleString() + '</b><span>个可比商品规格</span></div>' +
      '<div class="stat"><b>' + m.stats.items.toLocaleString() + '</b><span>条有效商品记录</span></div>' +
      '<div class="stat"><b>' + m.stats.merchants + '</b><span>家商家上榜</span></div>' +
      '</div>';
    h += '<div class="toolbar"><div class="row1">' +
      '<div class="search"><span class="ic">🔍</span>' +
      '<input id="q" type="search" placeholder="搜索品类或商品，如：爱奇艺 / 年卡 / 代金券" autocomplete="off">' +
      '<button class="clr" id="clr" title="清空">×</button></div>' +
      '<select class="sort" id="sort">' +
      '<option value="price">按最低价 ↑</option>' +
      '<option value="comp">按可比规格数 ↓</option>' +
      '<option value="merch">按商家数 ↓</option>' +
      '<option value="name">按名称</option>' +
      '</select></div>' +
      '<div class="chips" id="chips"></div></div>';
    h += '<div class="grid" id="grid"></div>';
    app.innerHTML = h;

    var chips = ['<span class="chip on" data-g="">全部<i>' + m.cats.length + '</i></span>'];
    m.groups.forEach(function (g) {
      chips.push('<span class="chip" data-g="' + esc(g.name) + '">' + esc(g.name) + '<i>' + g.count + '</i></span>');
    });
    $('#chips').innerHTML = chips.join('');

    var q = $('#q');
    var t = null;
    q.addEventListener('input', function () {
      $('#clr').style.display = q.value ? 'block' : 'none';
      clearTimeout(t);
      t = setTimeout(function () { F.q = q.value; updateGrid(); }, 130);
    });
    $('#clr').addEventListener('click', function () { q.value = ''; F.q = ''; $('#clr').style.display = 'none'; updateGrid(); q.focus(); });
    $('#sort').addEventListener('change', function () { F.sort = this.value; updateGrid(); });
    $('#chips').addEventListener('click', function (e) {
      var c = e.target.closest('.chip'); if (!c) return;
      F.group = c.getAttribute('data-g');
      var all = this.querySelectorAll('.chip');
      for (var i = 0; i < all.length; i++) all[i].className = 'chip';
      c.className = 'chip on';
      updateGrid();
    });
    $('#grid').addEventListener('click', function (e) {
      if (e.target.closest('a')) return;          // 卡片里的「去下单」按钮不触发进详情
      var card = e.target.closest('.card'); if (!card) return;
      location.hash = '#/c/' + card.getAttribute('data-i');
    });
  }

  function updateGrid() {
    var cats = S.meta.cats.slice();
    var sorter = {
      price: function (a, b) { return a.lo.p - b.lo.p; },
      comp: function (a, b) { return b.sc - a.sc || a.lo.p - b.lo.p; },
      merch: function (a, b) { return b.mc - a.mc || a.lo.p - b.lo.p; },
      name: function (a, b) { return a.kw.localeCompare(b.kw, 'zh'); }
    }[F.sort] || null;
    if (sorter) cats.sort(sorter);

    var q = F.q.trim().toLowerCase();
    var list = cats.filter(function (c) {
      if (F.group && c.group !== F.group) return false;
      if (!q) return true;
      return (c.kw + ' ' + c.group + ' ' + c.lo.n + ' ' + c.lo.s).toLowerCase().indexOf(q) >= 0;
    });

    var g = $('#grid');
    if (!list.length) { g.innerHTML = '<div class="empty">没有匹配的品类，换个词试试</div>'; return; }
    var base = S.meta.siteBase;
    g.innerHTML = list.map(function (c) {
      return '<div class="card" data-i="' + c.i + '">' +
        '<div class="top"><span class="kw">' + esc(c.kw) + '</span>' +
        '<span class="tag">' + esc(c.group) + '</span></div>' +
        '<div class="price">¥' + money(c.lo.p) + '<small>起</small></div>' +
        '<div class="shop"><b>' + esc(c.lo.s) + '</b>' + dv(c.lo.t) + '</div>' +
        '<div class="nm">' + esc(c.lo.n) + '</div>' +
        '<div class="foot"><span><b>' + c.mc + '</b> 家商家</span>' +
        '<span><b>' + c.sn + '</b> 规格</span>' +
        '<span><b>' + c.sc + '</b> 可比</span>' +
        (c.lo.u ? goLink(c.lo, c.kw, '去下单 ›') : '') +
        '</div>' +
        '</div>';
    }).join('');
  }

  /* ================= 品类详情 ================= */
  function loadCat(i) {
    var meta = S.meta.cats.filter(function (c) { return c.i === i; })[0];
    if (!meta) { location.hash = '#/'; return; }
    if (S.cache[i]) return renderCat(meta, S.cache[i]);
    app.innerHTML = '<div class="ld">正在载入「' + esc(meta.kw) + '」的商品数据</div>';
    fetch('data/cat/' + i + '.json').then(function (r) { return r.json(); }).then(function (d) {
      S.cache[i] = d;
      if (location.hash === '#/c/' + i) renderCat(meta, d);
    });
  }

  function renderCat(meta, d) {
    var comp = d.specs.filter(function (s) { return s.n >= 2; });
    var tail = d.specs.filter(function (s) { return s.n === 1; });
    S.cur = { meta: meta, d: d, comp: comp, tail: tail };

    // 有多少条报价拿到了「商家官网商品页直链」= 可一键去下单
    var nrow = 0, nbuy = 0;
    d.specs.forEach(function (s) {
      s.rows.forEach(function (r) { nrow++; if (r.u) nbuy++; });
    });

    var h = '<div class="crumb"><button class="back" id="back">← 返回</button>' +
      '<h2 class="title">' + esc(d.kw) + '<span class="tag">' + esc(d.group) + '</span></h2></div>';

    h += '<div class="stats">' +
      '<div class="stat"><b>¥' + money(meta.lo.p) + '</b><span>全网最低（' + esc(meta.lo.s) + '）</span></div>' +
      '<div class="stat"><b>' + comp.length + '</b><span>个可比规格（≥2 家）</span></div>' +
      '<div class="stat"><b>' + nbuy + '</b><span>条可一键下单（共 ' + nrow + ' 条报价）</span></div>' +
      '<div class="stat"><b>' + d.mc + '</b><span>家商家在售</span></div>' +
      '</div>';

    /* 一、商品规格比价（本站主体：同一件商品跨商家横比 + 一键去下单） */
    h += '<div class="panel"><h3>商品规格比价' +
      '<span class="hint">同一件商品（品牌+等级+时长）跨商家横比，标出全网最低；点“去下单”直接进商家商品页</span></h3>' +
      '<div style="padding:10px 14px;border-bottom:1px solid var(--bd);display:flex;gap:10px;flex-wrap:wrap">' +
      '<div class="search" style="flex:1;min-width:180px"><span class="ic">🔍</span>' +
      '<input id="gq" type="search" placeholder="在「' + esc(d.kw) + '」内筛选规格，如：年卡 / 月卡 / 5元" autocomplete="off"></div>' +
      '<select class="sort" id="gsort">' +
      '<option value="n">按在售家数 ↓</option>' +
      '<option value="lo">按最低价 ↑</option>' +
      '<option value="sd">按价差 ↓</option>' +
      '<option value="hi">按最高价 ↓</option>' +
      '</select>' +
      '<button class="back" id="toggleAll" type="button">全部展开</button>' +
      '</div>' +
      '<div id="specList"></div></div>';

    /* 二、长尾 */
    if (tail.length) {
      h += '<div class="panel"><details' + (comp.length ? '' : ' open') + '><summary style="padding:12px 15px;cursor:pointer;font-size:14.5px;font-weight:600">' +
        '只有 1 家在售的规格 <span class="hint" style="font-weight:400;color:var(--mut);font-size:12.5px">共 ' + tail.length + ' 个 · 看看这个品类还有哪些商品</span>' +
        '</summary><div class="tail">' +
        tail.map(function (s) {
          return '<span class="t">' + esc(s.sp.replace(/ · /g, '·')) + '<b>¥' + money(s.lo) + '</b></span>';
        }).join('') + '</div></details></div>';
    }

    h += '<div class="note">说明：价格取自抓取时刻快照，会随商家调价变动，下单前请以商家页面为准。' +
      '本页只保留<b>同款商品的跨商家比价</b>；点 <b>「去下单」</b> 直接打开该商家的商品下单页，' +
      '<b>「搜同款」</b> 表示只能打开该商家站内搜索结果，<b>「官网」</b> 表示该站不支持站内直达（多为需要登录的站）。' +
      '已剔除教程、引流、刷量等非卡券商品。</div>';

    app.innerHTML = h;
    $('#back').addEventListener('click', function () {
      if (history.length > 1) history.back(); else location.hash = '#/';
    });
    // 整行可点：跳到该商品的商家页面（委托一次即可，避免重复绑定）
    if (!renderCat.bound) {
      renderCat.bound = true;
      app.addEventListener('click', function (e) {
        if (e.target.closest('a') || e.target.closest('button')) return;
        var tr = e.target.closest('tr.rowgo'); if (!tr) return;
        var u = tr.getAttribute('data-href'); if (!u) return;
        window.open(u, '_blank', 'noopener');
      });
    }
    // details 展开时才注入表格（toggle 事件不冒泡，所以在捕获阶段接）
    if (!renderCat.tgbound) {
      renderCat.tgbound = true;
      app.addEventListener('toggle', fillLazy, true);
    }
    updateSpecs();

    var gq = $('#gq'), t2 = null;
    gq.addEventListener('input', function () {
      clearTimeout(t2);
      t2 = setTimeout(function () { G.q = gq.value; updateSpecs(); }, 130);
    });
    $('#gsort').addEventListener('change', function () { G.sort = this.value; updateSpecs(); });
    var ta = $('#toggleAll');
    if (ta) ta.addEventListener('click', function () {
      G.all = !G.all;
      this.textContent = G.all ? '全部收起' : '全部展开';
      updateSpecs();
    });
  }

  // 默认展开前几个规格。设为 0 = 一开始只列出各规格的标签行
  // （标签本身已带「N 家在售 / 最低 / 最高 / 价差」），要看哪家便宜再点开。
  var OPEN_N = 0;

  function updateSpecs() {
    var comp = S.cur.comp, kw = S.cur.d.kw;
    var q = G.q.trim().toLowerCase();
    var list = comp.filter(function (s) {
      if (!q) return true;
      return (s.sp + ' ' + s.rows.map(function (r) { return r.n + ' ' + r.s; }).join(' ')).toLowerCase().indexOf(q) >= 0;
    });
    var sorter = {
      n: function (a, b) { return b.n - a.n || a.lo - b.lo; },
      lo: function (a, b) { return a.lo - b.lo; },
      sd: function (a, b) { return b.sd - a.sd; },
      hi: function (a, b) { return b.hi - a.hi; }
    }[G.sort];
    if (sorter) list.sort(sorter);
    S.cur.list = list;                       // 懒渲染时按 data-si 回查

    if (!list.length) { $('#specList').innerHTML = '<div class="empty">没有匹配的规格</div>'; return; }

    $('#specList').innerHTML = list.map(function (s, si) {
      var parts = s.sp.split(' · ');
      var label = '<b>' + esc(parts[0]) + '</b>' + (parts.length > 1 ? ' · ' + esc(parts.slice(1).join(' · ')) : '');
      var open = (G.all || si < OPEN_N || !!q) ? ' open' : '';
      // 表格留空，展开时才注入（见 fillLazy）：一个品类可能有 500+ 行报价，
      // 全量渲染会把 DOM 顶到 8000+ 节点，手机上滚动、长按都会发涩。
      return '<details class="spec"' + open + ' data-si="' + si + '"><summary>' +
        '<span class="sp-name">' + label + '</span>' +
        '<span class="pill n">' + s.n + ' 家在售</span>' +
        '<span class="pill lo">最低 ¥' + money(s.lo) + '</span>' +
        '<span class="pill hi">最高 ¥' + money(s.hi) + '</span>' +
        '<span class="pill sd">价差 ' + Math.round(s.sd) + '%</span>' +
        '</summary><div class="lz"></div></details>';
    }).join('');
    fillLazy();
  }

  /* 只给「已展开」的规格块生成表格 DOM */
  function fillLazy() {
    var boxes = document.querySelectorAll('#specList details.spec');
    var list = (S.cur && S.cur.list) || [];
    for (var i = 0; i < boxes.length; i++) {
      var d = boxes[i];
      if (!d.open) continue;
      var box = d.querySelector('.lz');
      if (!box || box.firstChild) continue;
      var s = list[+d.getAttribute('data-si')];
      if (s) box.innerHTML = tableHTML(s);
    }
  }

  function tableHTML(s) {
    var kw = S.cur.d.kw;
    var body = s.rows.map(function (r, i) {
      return '<tr class="' + (i === 0 ? 'best' : '') + ' rowgo" data-href="' + esc(rowHref(r, kw)) + '">' +
        '<td class="rank">' + (i + 1) + '</td>' +
        '<td>' + esc(r.s) + '</td>' +
        '<td class="num"><b>¥' + money(r.p) + '</b></td>' +
        '<td class="hide-sm">' + dv(r.t) + '</td>' +
        '<td class="nm2">' + esc(r.n) + '</td>' +
        '<td>' + goLink(r, kw) + '</td></tr>';
    }).join('');
    return '<table><thead><tr><th>#</th><th>商家</th><th>价格</th>' +
      '<th class="hide-sm">交付</th><th>商品名</th><th>下单</th></tr></thead>' +
      '<tbody>' + body + '</tbody></table>';
  }

  /* ================= 商家榜 ================= */
  function renderMerch() {
    var ms = S.merchants;
    var max = Math.max.apply(null, ms.map(function (m) { return m.sw; })) || 1;
    app.innerHTML =
      '<h2 class="title" style="margin-bottom:14px">商家榜<span class="tag">按拿下多少品类的全网最低价排</span></h2>' +
      '<div class="panel"><h3>谁最便宜？' +
      '<span class="hint">「品类冠军」= 该商家在某品类里报了全网最低价；「规格冠军」= 拿下的同款商品数</span></h3>' +
      '<table><thead><tr><th>#</th><th>商家</th><th>品类冠军</th><th>规格冠军</th>' +
      '<th class="hide-sm">覆盖品类</th><th class="hide-sm">进前三</th><th class="hide-sm">站点</th></tr></thead><tbody>' +
      ms.map(function (m, i) {
        return '<tr class="' + (i === 0 ? 'best' : '') + '">' +
          '<td class="rank">' + (i + 1) + '</td>' +
          '<td><b>' + esc(m.n) + '</b></td>' +
          '<td class="num"><b>' + m.wins + '</b></td>' +
          '<td class="num" title="拿下的同款商品数">' + m.sw +
          '<span style="display:inline-block;width:60px;height:5px;border-radius:3px;background:var(--bd2);margin-left:8px;vertical-align:middle;position:relative;overflow:hidden">' +
          '<i style="position:absolute;left:0;top:0;bottom:0;width:' + Math.round(m.sw / max * 100) + '%;background:var(--acc);border-radius:3px"></i></span></td>' +
          '<td class="hide-sm num">' + m.appear + '</td>' +
          '<td class="hide-sm num">' + m.top3 + '</td>' +
          '<td class="hide-sm"><a class="go' + (merchantDirect(m.id) ? ' direct' : '') + '" href="' + esc(merchantHref(m.id, '')) + '" target="_blank" rel="noopener nofollow">去逛逛 ›</a></td>' +
          '</tr>';
      }).join('') + '</tbody></table></div>' +
      '<div class="note">说明：同一商家若在不同系统下有多个站点，会分别出现。「品类冠军」统计口径为品类中该商家的最低单品与全网最低持平。</div>';
  }

  /* ================= 说明页 ================= */
  function renderAbout() {
    var m = S.meta;
    var directN = 0, totalN = 0;
    for (var k in S.sites) { totalN++; if (S.sites[k] && S.sites[k].v) directN++; }
    app.innerHTML =
      '<h2 class="title" style="margin-bottom:14px">这个站是怎么来的</h2>' +
      '<div class="panel" style="padding:16px 18px">' +
      '<div class="note">' +
      '<p><b>数据源。</b>kaquanjishi.com 是一个卡券商家导航站，它自己不出货，但提供了一个「批量查价」接口，会按关键词去各家卡商实时抓价。本站复用了这个接口，批量抓取了 ' +
      m.stats.cats + ' 个品类、' + m.stats.items.toLocaleString() + ' 条有效商品记录，再横向拉平对比。</p>' +
      '<p><b>两个层级，别混着看。</b></p>' +
      '<p>① <b>品类速查</b>：首页每个卡片给出该品类「最便宜的那件」是哪家，用来快速扫一眼大盘。注意它<b>不是同一件商品</b>——A 家最便宜可能是 1 天共享号，B 家最便宜可能是月卡，直接比数字会误导。</p>' +
      '<p>② <b>商品规格比价</b>（本站主体）：把同一件商品的不同写法归并（面额/杯型/口味/时长/等级），得出真正<b>同款</b>的跨商家最低价。要抄结论就看这里。' +
      '<b>点「去下单」或整行</b>，会直接打开该商家官网的<b>商品下单页</b>，不用再经过聚合站的中转页、也不用在商家首页里自己找。' +
      '拿不到商品直链时会退化为「搜同款」（打开该商家的站内搜索结果）或「官网」（只能到首页，多为需要登录的站）。' +
      '全站 ' + totalN + ' 家商家里有 ' + directN + ' 家支持站内直达。</p>' +
      '<p><b>交付方式要看清。</b>' + 
      '<span class="dv dv-直充">直充</span> 充到你自己账号；' +
      '<span class="dv dv-共享号">共享号</span> 是共享账号，最便宜但账号共用；' +
      '<span class="dv dv-卡密兑换码">卡密/兑换码</span> 需自行兑换；' +
      '<span class="dv dv-代下单">代下单</span> 由商家代替下单。同价不同货。</p>' +
      '<p><b>已做的清洗。</b>原始数据里混有大量教程、课程、引流项目、刷播放量/粉丝、盗版资源、商品说明页，以及商家标错的占位价，均已剔除。但快照价格会变动，下单前以商家页面为准。</p>' +
      '<p><b>口径。</b>当前收录 ' + m.stats.merchants + ' 家出现在结果中的商家、' + m.stats.specs.toLocaleString() + ' 个商品规格，其中 ' + m.stats.comp.toLocaleString() + ' 个有 ≥2 家在售、可横比。数据时间：' + esc(m.generated) + '。</p>' +
      '<p><b>自动更新。</b>本站由服务端定时重新抓取全部品类并重算比价，数据会自动刷新，无需手动操作。页面右上角的绿点表示自动更新已开启；想立刻拉一次最新数据，点旁边的 ↻ 按钮即可。若价格与商家页面不符，以商家页面为准。</p>' +
      '</div></div>';
  }

  /* ================= 状态 / 自动更新 ================= */
  var toastTimer = null;
  function toast(msg) {
    var el = $('#toast'); if (!el) return;
    el.textContent = msg;
    el.className = 'toast on';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.className = 'toast'; }, 3400);
  }

  /* 本站是纯静态站，没有 /api/status 这类后端接口。
     旧版启动时先打一个 /api/status：它是 404，实测耗时约 1 秒、还要下载 8KB
     surge 404 页面，并且串在所有数据加载之前 —— 这是首屏"半天加载不出来"的主因。
     现在改为：数据时间直接读内联的 meta.generated，不发任何状态请求。 */
  function paintStatus() {
    var stamp = $('#stamp'), live = $('#live');
    if (stamp && S.meta) stamp.textContent = '数据更新 ' + (S.meta.generated || '');
    if (live) live.title = '数据由服务端定时自动重抓';
  }

  /* 按文件重新拉取数据（仅用于右上角「刷新数据」按钮） */
  function fetchFresh() {
    var v = '?v=' + Date.now();
    return Promise.all([
      fetch('data/meta.json' + v, { cache: 'no-store' }).then(function (r) { return r.json(); }),
      fetch('data/merchants.json' + v, { cache: 'no-store' }).then(function (r) { return r.json(); }),
      fetch('data/sites.json' + v, { cache: 'no-store' }).then(function (r) { return r.json(); }).catch(function () { return {}; })
    ]).then(function (a) {
      S.meta = a[0]; S.merchants = a[1]; S.sites = a[2] || {}; S.cache = {}; S.cur = null;
      paintStatus();
    });
  }

  /* ================= 启动 =================
     首屏数据由 build_shell.py 内联进 window.__BOOT__：打开即可渲染，
     首屏不再发任何额外数据请求（这是解决"半天加载不出来"的关键）。
     若没有内联（例如直接用浏览器打开 site/index.html 调试），回退到按文件拉取。 */
  function start() {
    var boot = window.__BOOT__;
    var ready;
    if (boot && boot.meta) {
      S.meta = boot.meta;
      S.merchants = boot.merchants || [];
      S.sites = boot.sites || {};
      ready = Promise.resolve();
    } else {
      ready = Promise.all([
        fetch('data/meta.json').then(function (r) { return r.json(); }),
        fetch('data/merchants.json').then(function (r) { return r.json(); }),
        fetch('data/sites.json').then(function (r) { return r.json(); }).catch(function () { return {}; })
      ]).then(function (a) {
        S.meta = a[0]; S.merchants = a[1]; S.sites = a[2] || {};
      });
    }
    ready.then(function () {
      paintStatus();
      var rf = $('#rf');
      if (rf) rf.addEventListener('click', function () {
        if (this.className.indexOf('busy') >= 0) return;
        var self = this;
        self.className = 'rf busy';
        toast('正在拉取最新数据…');
        fetchFresh().then(function () {
          route();
          toast('已更新 · ' + (S.meta.generated || ''));
        }).catch(function () {
          toast('拉取失败，请稍后再试');
        }).then(function () { self.className = 'rf'; });
      });
      window.addEventListener('hashchange', route);
      route();
    }).catch(function (e) {
      app.innerHTML = '<div class="empty">数据载入失败：' + esc(e.message) +
        '<br><br>请通过本地服务器打开（file:// 无法读取数据文件）。</div>';
    });
  }

  start();
})();
