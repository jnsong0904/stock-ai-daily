/* ===== 证券业 AI 动态日报 · 前端逻辑 ===== */
const HOLIDAYS_2026 = new Set([
  "2026-01-01","2026-01-02","2026-02-16","2026-02-17","2026-02-18","2026-02-19","2026-02-20",
  "2026-04-03","2026-04-04","2026-04-05","2026-04-06","2026-05-01","2026-05-02","2026-05-03",
  "2026-05-04","2026-05-05","2026-06-19","2026-09-25","2026-10-01","2026-10-02","2026-10-03",
  "2026-10-04","2026-10-05","2026-10-06","2026-10-07","2026-12-25"
]);

function bjYear(){
  const now = new Date();
  const asUTC = new Date(now.getTime() + now.getTimezoneOffset()*60000);
  return new Date(asUTC.getTime() + 8*3600*1000).getFullYear();
}
function beijing(iso, withYear){
  if(!iso) return "";
  const s = iso.replace("Z","+00:00");
  const dt = new Date(s);
  const asUTC = new Date(dt.getTime() + dt.getTimezoneOffset()*60000);
  const bj = new Date(asUTC.getTime() + 8*3600*1000);
  const p = n => String(n).padStart(2,"0");
  const yr = bj.getFullYear();
  if(withYear === undefined) withYear = (yr !== bjYear());
  return (withYear ? yr + "-" : "") + `${p(bj.getMonth()+1)}-${p(bj.getDate())} ${p(bj.getHours())}:${p(bj.getMinutes())}`;
}
function isTradingDay(dateStr){
  const [y,m,d] = dateStr.split("-").map(Number);
  const day = new Date(y, m-1, d).getDay();
  if(day === 0 || day === 6) return false;
  return !HOLIDAYS_2026.has(dateStr);
}
function typeInfo(t){
  if(t === "产品功能") return {cls:"feature", label:"产品功能"};
  if(t === "Skill建设") return {cls:"skill", label:"Skill建设"};
  if(t === "未来规划") return {cls:"plan", label:"未来规划"};
  if(t === "法律合规") return {cls:"compliance", label:"法律合规"};
  if(!t || t === "其他") return {cls:"feature", label:"产品功能"};
  return {cls:"feature", label:t};
}

/* 数据来源渠道：App Store / 微信公众号 / 全网新闻（AI 联网搜索） */
function sourceInfo(ch){
  if(ch === "App Store") return {cls:"src-app", label:"App Store"};
  if(ch === "微信公众号") return {cls:"src-wechat", label:"微信公众号"};
  return {cls:"src-web", label:"全网新闻"};
}
function sourceChannel(it){
  if(it.sourceType) return it.sourceType;
  const s = it.source || "";
  if(s.includes("App Store")) return "App Store";
  if(s.includes("公众号")) return "微信公众号";
  return "全网新闻";
}
const ALL_CHANNELS = ["App Store", "微信公众号", "全网新闻"];
function todayBJ(){
  const now = new Date();
  const asUTC = new Date(now.getTime() + now.getTimezoneOffset()*60000);
  const bj = new Date(asUTC.getTime() + 8*3600*1000);
  const p = n => String(n).padStart(2,"0");
  return `${bj.getFullYear()}-${p(bj.getMonth()+1)}-${p(bj.getDate())}`;
}
function esc(s){ return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

let DATA = null;
async function loadData(){
  if(DATA) return DATA;
  // 数据真相源是 github.io（GitHub Actions 每日更新）。所有前台（github.io / CloudStudio / jsDelivr）
  // 统一从这里拉最新数据；github.io 不可达时回退本地 ./data/data.json。
  const SRC = "https://jnsong0904.github.io/stock-ai-daily/data/data.json";
  try {
    const r = await fetch(SRC, {cache:"no-store"});
    if(r.ok){ const j = await r.json(); if(j && j.items){ DATA = j; return DATA; } }
  } catch(e){ /* 回退本地 */ }
  const res = await fetch("./data/data.json", {cache:"no-store"});
  DATA = await res.json();
  return DATA;
}

// 详情页【完整内容】只展示前 1-2 段，避免长文堆砌；完整内容走「查看原文」。
function truncateContent(c){
  if(!c) return "";
  const paras = String(c).split(/\n+/).map(p=>p.trim()).filter(Boolean);
  let head = paras.slice(0,2).join("\n");
  if(head.length > 560) head = head.slice(0,560) + "…";
  return head;
}

function rowHTML(it){
  const ti = typeInfo(it.type);
  const si = sourceInfo(sourceChannel(it));
  return `<a class="row" href="detail.html?id=${encodeURIComponent(it.id)}">
    <div class="bar" style="background:var(${ti.cls==='feature'?'--t-feature':ti.cls==='skill'?'--t-skill':'--t-plan'})"></div>
    <div class="main">
      <div class="title">${esc(it.title)}</div>
      <div class="meta">
        <span class="broker${it.broker==="证券业"?" broker-industry":""}">${esc(it.broker)}</span>
        ${it.app?`<span class="chip-soft">${esc(it.app)}</span>`:""}
        ${it.module?`<span class="chip-soft">${esc(it.module)}</span>`:""}
        <span class="tag src ${si.cls}" title="数据来源：${esc(si.label)}">${si.label}</span>
        ${it.backfill?`<span class="chip-flag backfill" title="原文发布已超过 30 天，为补录条目">补录</span>`:""}
        ${it.timeInferred?`<span class="chip-flag inferred" title="原文无可解析发布时间，此处以采集日推断">时间推断</span>`:""}
      </div>
      <div class="summary">${esc(it.summary)}</div>
    </div>
    <div class="side">
      <span class="tag type ${ti.cls}">${ti.label}</span>
      <span class="time">${beijing(it.publishedAt)}</span>
      ${typeof it.ageDays === "number" && it.ageDays > 0 ? `<span class="age">${it.ageDays} 天前</span>` : ""}
    </div>
  </a>`;
}

function renderFeed(el, items){
  if(!items.length){ el.innerHTML = `<div class="empty">没有匹配的动态</div>`; return; }
  el.innerHTML = items.map(rowHTML).join("");
}

/* 采集窗口：展示每个数据源的采集数量与成功/失败状态 */
function renderCollectWindow(el, header, items, reports){
  if(!el) return;
  const byCh = {};
  items.forEach(it => { const ch = sourceChannel(it); byCh[ch] = (byCh[ch]||0)+1; });
  const statusMap = {};
  (reports||[]).forEach(r => (r.sources||[]).forEach(s => { statusMap[s.channel] = s; }));

  const rows = ALL_CHANNELS.map(ch => {
    const n = byCh[ch] || 0;
    const rep = statusMap[ch];
    const st = rep ? rep.status : (n > 0 ? "success" : "empty");
    const note = rep ? (rep.note || rep.error || "") : "";
    return {ch, n, st, note};
  });
  const okN = rows.filter(r => r.st === "success").length;
  const failN = rows.filter(r => r.st === "failed").length;
  const statusText = {success:"成功", failed:"失败", empty:"无数据", partial:"部分成功"};

  el.style.display = "flex";
  el.innerHTML = `
    <div class="cw-head">
      <span class="cw-title">📡 采集窗口</span>
      <span class="cw-range">${esc(header)}</span>
      <span class="cw-summary">${okN} 源成功${failN?` · <b style="color:#b91c1c">${failN} 源失败</b>`:""}</span>
    </div>
    <div class="cw-rows">
      ${rows.map(r => `
        <div class="cw-row">
          <span class="cw-dot s-${r.st}"></span>
          <span class="cw-name">${esc(r.ch)}</span>
          <span class="cw-count">${r.n} 条</span>
          <span class="cw-status s-${r.st}">${statusText[r.st]||r.st}</span>
          ${r.note?`<span class="cw-note" title="${esc(r.note)}">${esc(r.note)}</span>`:""}
        </div>`).join("")}
    </div>`;
}

/* 分页：首页/归档页列表 50 条/页 */
const PAGE_SIZE = 50;
function pagerBarHTML(total, page){
  const pages = Math.max(1, Math.ceil(total/PAGE_SIZE));
  if(pages<=1) return "";
  const p = Math.min(Math.max(1,page), pages);
  const start=(p-1)*PAGE_SIZE+1, end=Math.min(p*PAGE_SIZE,total);
  return `<div class="pager"><button type="button" data-pg="${p-1}" ${p<=1?'disabled':''}>‹ 上一页</button><span>第 ${p}/${pages} 页 · ${start}-${end} / 共 ${total} 条</span><button type="button" data-pg="${p+1}" ${p>=pages?'disabled':''}>下一页 ›</button></div>`;
}
/* ---------- 首页 ---------- */
async function initIndex(){
  const {meta, items} = await loadData();
  // 首页按「首次发现日」而非「原文发生日」聚合：
  // 今天新发现的一条上月动态，仍应出现在今日日报里；归档页才按发生日浏览。
  const seenDates = (meta.firstSeenDates && meta.firstSeenDates.length)
    ? meta.firstSeenDates : meta.dates;
  const homeDate = seenDates[0];
  const realToday = todayBJ();
  const trading = isTradingDay(realToday);

  document.getElementById("homeDate").textContent = homeDate;
  const [hy,hm,hd] = homeDate.split("-").map(Number);
  document.getElementById("homeWeekday").textContent = "周" + "日一二三四五六"[new Date(hy, hm-1, hd).getDay()];
  const badge = document.getElementById("tradeBadge");
  badge.textContent = trading ? "交易日" : "休市";
  badge.className = "badge " + (trading ? "open" : "closed");

  const dayItems = items.filter(i=>(i.firstSeenDate || i.date)===homeDate);

  document.getElementById("kTotal").textContent = dayItems.length;
  document.getElementById("kBroker").textContent = new Set(dayItems.map(i=>i.broker)).size;
  document.getElementById("kType").textContent = meta.types.length;

  const note = document.getElementById("homeNote");
  if(note){
    if(homeDate !== realToday){
      note.style.display = "flex";
      note.textContent = `以下为最近一期新发现（${homeDate}）${trading?"，今日数据尚未采集发布":"，今日休市不更新"}。`;
    } else {
      note.style.display = "none";
    }
  }

  // 采集窗口（每数据源数量 + 成功/失败）
  const reports = (meta.collectionReports && meta.collectionReports[homeDate]) ? [meta.collectionReports[homeDate]] : null;
  let cwHeader = "";
  if(reports && reports[0]){
    cwHeader = `${reports[0].since.slice(5,16).replace("T"," ")} → ${reports[0].until.slice(5,16).replace("T"," ")}（回溯至 ${reports[0].prevTradingDay}）`;
  }else if(meta.lastWindow && meta.lastWindow.spanHours){
    cwHeader = `${meta.lastWindow.since.slice(5,16).replace("T"," ")} → ${meta.lastWindow.until.slice(5,16).replace("T"," ")}`;
  }
  renderCollectWindow(document.getElementById("collectWindow"), cwHeader, dayItems, reports);

  const feed = document.getElementById("feed");
  const typeSeg = document.getElementById("typeSeg");
  const brokerSel = document.getElementById("brokerSel");
  const srcSel = document.getElementById("srcSel");
  // 分类分段按 meta.types 动态生成（与历史归档页一致）
  typeSeg.innerHTML = `<button value="" class="active">全部</button>` +
    meta.types.map(t=>`<button value="${esc(t)}">${esc(t)}</button>`).join("");
  typeSeg.value = "";
  brokerSel.innerHTML = `<option value="">全部券商</option>` + meta.brokers.map(b=>`<option value="${esc(b)}">${esc(b)}</option>`).join("");
  // 数据来源筛选（固定三渠道）
  srcSel.innerHTML = `<option value="">全部来源</option>` +
    ALL_CHANNELS.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join("");

  let page = 1;
  function getList(){
    const t = typeSeg.value;
    const br = brokerSel.value;
    const sc = srcSel.value;
    let list = dayItems;
    if(t) list = list.filter(i=>i.type===t);
    if(br) list = list.filter(i=>i.broker===br);
    if(sc) list = list.filter(i=>sourceChannel(i)===sc);
    return list.slice().sort((a,b)=> (b.publishedAt||"").localeCompare(a.publishedAt||""));
  }
  function repaint(){
    const list = getList();
    const pages = Math.max(1, Math.ceil(list.length/PAGE_SIZE));
    if(page>pages) page = pages;
    const slice = list.slice((page-1)*PAGE_SIZE, page*PAGE_SIZE);
    renderFeed(feed, slice);
    feed.insertAdjacentHTML("beforeend", pagerBarHTML(list.length, page));
    document.getElementById("cnt").textContent = list.length;
  }
  function apply(){ page = 1; repaint(); }
  typeSeg.addEventListener("change", apply);
  brokerSel.addEventListener("change", apply);
  srcSel.addEventListener("change", apply);
  feed.addEventListener("click", e=>{
    const b = e.target.closest("button[data-pg]"); if(!b) return;
    const p = parseInt(b.dataset.pg,10); if(!isNaN(p) && p>=1){ page=p; repaint(); }
  });
  apply();
}

/* ---------- 日历区间选择器（归档页用） ---------- */
function initDatePicker(availableDates){
  /* availableDates: string[] 如 ["2026-08-10","2026-07-27",...], 已排序 */
  const picker = document.getElementById("datePicker");
  const display = document.getElementById("drpDisplay");
  const cal = document.getElementById("drpCalendar");
  const fromInput = document.getElementById("dateFrom");
  const toInput = document.getElementById("dateTo");

  if(!picker || !cal) return;

  let selStart = null, selEnd = null;       // 选中的起止日期 "YYYY-MM-DD"
  let viewYear, viewMonth;                   // 日历当前显示的年月
  const dateSet = new Set(availableDates);
  // 可选范围：最早数据日 ~ 今天
  const minDate = availableDates[0] || "";
  const maxDate = todayBJ();                 // 修复：允许选到今天

  function renderCalendar(){
    const y = viewYear, m = viewMonth;
    const firstDay = new Date(y, m, 1).getDay();   // 0=Sun
    const daysInMonth = new Date(y, m+1, 0).getDate();
    const todayStr = todayBJ();

    let html = `<div class="drp-nav">
      <button type="button" class="drp-prev" data-delta="-1">◀</button>
      <span class="drp-month">${y}年${m+1}月</span>
      <button type="button" class="drp-next" data-delta="1">▶</button>
    </div>
    <div class="drp-weekdays"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
    <div class="drp-days">`;

    // 空白填充（周一起始，firstDay=0(Sun)时前面6格，firstDay=1(Mon)时0格）
    const pad = (firstDay + 6) % 7;

    // 收集所有单元格，每7个包一个 drp-week 行（显式行包裹，避免 CSS Grid 跨浏览器排列差异）
    let cells = [];
    for(let i=0;i<pad;i++) cells.push(`<span class="drp-day empty"></span>`);

    for(let d=1;d<=daysInMonth;d++){
      const ds = `${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const isToday = ds === todayStr;
      const hasData = dateSet.has(ds);
      const inRange = selStart && selEnd && ds >= selStart && ds <= selEnd;
      const isStart = ds === selStart;
      const isEnd = ds === selEnd;
      // 允许选的范围：不早于 minDate，不晚于 maxDate
      const outOfRange = ds < minDate || ds > maxDate;

      let cls = "drp-day";
      if(outOfRange) cls += " out";
      else if(isToday) cls += " today";
      if(hasData && !outOfRange) cls += " has-data";
      if(inRange && !outOfRange) cls += " in-range";
      if(isStart) cls += " start";
      if(isEnd) cls += " end";

      cells.push('<span class="'+cls+'" data-date="'+ds+'" '+(outOfRange?"tabindex='-1'":" tabindex='0'")+'>'+d+'</span>');
    }

    // 每7个一行
    for(let i=0;i<cells.length;i+=7){
      html += `<div class="drp-week">${cells.slice(i,i+7).join("")}</div>`;
    }

    html += `</div>`;
    if(selStart || selEnd){
      html += `<div class="drp-actions">
        <button type="button" class="drp-clear">清除</button>
        <span class="drp-sel-text">${selStart||"—"} ~ ${selEnd||"—"}</span>
      </div>`;
    }
    cal.innerHTML = html;
  }

  function showCal(){
    cal.style.display = "";
    if(viewYear==null){
      const now = new Date();
      // 默认显示最新有数据的月份，或今天所在月
      const latest = availableDates[availableDates.length-1];
      if(latest){
        viewYear = parseInt(latest.split("-")[0]);
        viewMonth = parseInt(latest.split("-")[1])-1;
      }else{
        viewYear = now.getFullYear();
        viewMonth = now.getMonth();
      }
    }
    renderCalendar();
  }
  function hideCal(){ cal.style.display = "none"; }

  function pickDate(ds){
    if(dateSet.has(ds) || ds <= maxDate){   // 有数据的日期或范围内任意日期均可点
      if(!selStart || (selStart && selEnd)){
        selStart = ds; selEnd = null;
      } else {
        if(ds < selStart){ selEnd = selStart; selStart = ds; }
        else selEnd = ds;
      }
      fromInput.value = selStart || "";
      toInput.value = selEnd || "";
      updateDisplayLabel();
      renderCalendar();
      fromInput.dispatchEvent(new Event("change"));
      toInput.dispatchEvent(new Event("change"));
    }
  }

  function updateDisplayLabel(){
    if(selStart && selEnd){
      display.innerHTML = `<span class="drp-label">${selStart.slice(5)} ~ ${selEnd.slice(5)}</span><span class="drp-arrow">▾</span>`;
    } else if(selStart){
      display.innerHTML = `<span class="drp-label">${selStart.slice(5)} 起</span><span class="drp-arrow">▾</span>`;
    } else {
      display.innerHTML = `<span class="drp-label">选择日期范围</span><span class="drp-arrow">▾</span>`;
    }
  }

  // 事件绑定
  display.addEventListener("click", e => {
    e.stopPropagation();
    if(cal.style.display==="none") showCal(); else hideCal();
  });
  cal.addEventListener("click", e => {
    e.stopPropagation();
    const t = e.target.closest("[data-date]");
    if(t && !t.classList.contains("out")){
      pickDate(t.dataset.date);
    }
    const prev = e.target.closest(".drp-prev");
    const next = e.target.closest(".drp-next");
    if(prev){ viewMonth--; if(viewMonth<0){viewMonth=11;viewYear--;} renderCalendar(); }
    if(next){ viewMonth++; if(viewMonth>11){viewMonth=0;viewYear++;} renderCalendar(); }
    const clearBtn = e.target.closest(".drp-clear");
    if(clearBtn){ selStart=null; selEnd=null; fromInput.value=""; toInput.value=""; updateDisplayLabel(); renderCalendar(); fromInput.dispatchEvent(new Event("change")); toInput.dispatchEvent(new Event("change")); }
  });
  document.addEventListener("click", e => { if(!picker.contains(e.target)) hideCal(); });

  // 公开方法供外部读取值
  picker._getRange = () => ({from: selStart, to: selEnd});
}
async function initArchive(){
  const {meta, items} = await loadData();
  const fromInput = document.getElementById("dateFrom");
  const toInput = document.getElementById("dateTo");
  const brokerSel = document.getElementById("brokerSel");
  const typeSel = document.getElementById("typeSel");
  const srcSel = document.getElementById("srcSel");
  const search = document.getElementById("search");
  const feed = document.getElementById("feed");
  const cnt = document.getElementById("cnt");

  // 初始化日历区间选择器（替代原来的两个 <input type=date>）
  const allDates = meta.dates.slice().sort();
  initDatePicker(allDates);

  brokerSel.innerHTML = `<option value="">全部券商</option>` + meta.brokers.map(b=>`<option value="${esc(b)}">${esc(b)}</option>`).join("");
  typeSel.innerHTML = `<option value="">全部分类</option>` + meta.types.map(t=>`<option value="${esc(t)}">${esc(t)}</option>`).join("");
  srcSel.innerHTML = `<option value="">全部来源</option>` + ALL_CHANNELS.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join("");

  let page = 1;
  function getList(){
    const ff = fromInput.value, tt = toInput.value;
    const br = brokerSel.value, ty = typeSel.value, sc = srcSel.value;
    const q = search.value.trim().toLowerCase();
    let list = items;
    if(ff) list = list.filter(i=> (i.date||"") >= ff);
    if(tt) list = list.filter(i=> (i.date||"") <= tt);
    if(br) list = list.filter(i=>i.broker===br);
    if(ty) list = list.filter(i=>i.type===ty);
    if(sc) list = list.filter(i=>sourceChannel(i)===sc);
    if(q) list = list.filter(i =>
      (i.title+i.summary+i.content+i.broker+(i.app||"")+(i.module||"")+(i.tags||[]).join("")).toLowerCase().includes(q));
    return list.slice().sort((a,b)=> (b.publishedAt||"").localeCompare(a.publishedAt||""));
  }
  function repaint(){
    const list = getList();
    const pages = Math.max(1, Math.ceil(list.length/PAGE_SIZE));
    if(page>pages) page = pages;
    const slice = list.slice((page-1)*PAGE_SIZE, page*PAGE_SIZE);
    renderFeed(feed, slice);
    feed.insertAdjacentHTML("beforeend", pagerBarHTML(list.length, page));
    cnt.textContent = list.length;
  }
  function apply(){
    page = 1;
    // 采集窗口渲染（按日期区间）
    const f = fromInput.value, t = toInput.value;
    let cwItems = items;
    if(f) cwItems = cwItems.filter(i=> (i.date||"") >= f);
    if(t) cwItems = cwItems.filter(i=> (i.date||"") <= t);
    const reports = meta.collectionReports
      ? Object.keys(meta.collectionReports).filter(d => (!f || d >= f) && (!t || d <= t)).sort().map(d => meta.collectionReports[d])
      : null;
    const hdr = (f||t) ? `所选区间：${f||"最早"} ~ ${t||"最新"}` : "全部日期";
    renderCollectWindow(document.getElementById("collectWindow"), hdr, cwItems, reports);
    repaint();
  }
  [fromInput,toInput,brokerSel,typeSel,srcSel].forEach(s=>s.addEventListener("change",apply));
  search.addEventListener("input", apply);
  feed.addEventListener("click", e=>{
    const b = e.target.closest("button[data-pg]"); if(!b) return;
    const p = parseInt(b.dataset.pg,10); if(!isNaN(p) && p>=1){ page=p; repaint(); }
  });
  apply();
}

/* ---------- 详情 ---------- */
async function initDetail(){
  const {items} = await loadData();
  const id = new URLSearchParams(location.search).get("id");
  const it = items.find(x=>x.id===id);
  const root = document.getElementById("detail");
  if(!it){ root.innerHTML = `<div class="empty">未找到该动态（id=${esc(id)}）</div>`; return; }
  const ti = typeInfo(it.type);
  const an = it.analysis || {};
  const aKeys = Object.keys(an);
  root.innerHTML = `
    <h1>${esc(it.title)}</h1>
    <div class="meta-grid">
      <div class="cell"><div class="k">券商名称</div><div class="v">${esc(it.broker)}</div></div>
      <div class="cell"><div class="k">涉及产品</div><div class="v">${esc(it.app||"—")}</div></div>
      <div class="cell"><div class="k">产品模块</div><div class="v">${esc(it.module||"—")}</div></div>
      <div class="cell"><div class="k">动态类型</div><div class="v" style="color:var(${ti.cls==='feature'?'--t-feature':ti.cls==='skill'?'--t-skill':'--t-plan'})">${ti.label}</div></div>
      <div class="cell"><div class="k">发布时间</div><div class="v">${beijing(it.publishedAt)}${it.timeInferred?` <span class="chip-flag inferred">采集推断</span>`:""}</div></div>
      <div class="cell"><div class="k">采集时间</div><div class="v">${beijing(it.collectedAt)}</div></div>
      <div class="cell"><div class="k">归档日期</div><div class="v">${esc(it.date)}<span class="age"> · 按发布日</span></div></div>
      <div class="cell"><div class="k">首次发现</div><div class="v">${esc(it.firstSeenDate||it.date)}${typeof it.ageDays==="number"?`<span class="age"> · 滞后 ${it.ageDays} 天</span>`:""}</div></div>
      <div class="cell"><div class="k">新鲜度</div><div class="v">${it.backfill?`<span class="chip-flag backfill">补录（>30 天）</span>`:"当期"}</div></div>
      <div class="cell"><div class="k">来源</div><div class="v">${esc(it.source||"—")}</div></div>
    </div>
    ${it.timeInferred?`<div class="banner info" style="margin:12px 0">该条动态原文未提供可解析的发布时间，此处以采集日推断，不代表官方发布时间。</div>`:""}
    <div class="section-h">内容摘要</div>
    <div class="detail-content">${esc(it.summary)}</div>
    <div class="section-h">完整内容</div>
    <div class="detail-content">${esc(truncateContent(it.content))}</div>
    ${String(it.content||"").trim().length > truncateContent(it.content).length ? `<div class="age" style="margin:4px 0 0">仅展示前 1-2 段，完整内容见「查看原文」</div>`:""}
    ${aKeys.length?`<div class="section-h">结构化解读</div><div class="analysis">`+
      aKeys.map(k=>`<div class="a-item"><div class="ak">${esc(k)}</div><div class="av">${esc(an[k])}</div></div>`).join("")+`</div>`:""}
    ${it.tags&&it.tags.length?`<div class="section-h">标签</div><div style="display:flex;gap:8px;flex-wrap:wrap">`+
      it.tags.map(t=>`<span class="chip-soft">${esc(t)}</span>`).join("")+`</div>`:""}
    <a class="btn-orig" href="${esc(it.sourceUrl||"#")}" target="_blank" rel="noopener noreferrer">查看原文 →</a>
  `;
  document.title = it.title + " · 证券业 AI 动态日报";
}

/* ---------- 竞品对比矩阵 ---------- */

/* 模块归类体系：将零散原始模块归纳为 6 大能力域 */
const MODULE_CATS = {
  "智能投研/投顾":   ["超级研究员 / CapitAI-Link","智能诊股","投顾赋能","AI+人工投顾","Alice 27 / EDB"],
  "智能交易/执行":   ["盯盘 / 交易 / 对话","AI原生交易终端","i助理 / i盯盘 / i交易","任务助手 / 智能盯盘","行情交易"],
  "智能客服/运营":   ["微信生态 / 多专家Agent","大模型面客 / 服务规模"],
  "大模型基础/平台":  ["智能体生态","人工智能平台","大模型本地化","技能体系","综合平台"],
  "财富管理":        ["财富管理"],
  "合规风控/投行":    ["合规风控","投行数字化"]
};
// 反查：原始模块 → 归类
function moduleCat(raw){
  for(const [cat, members] of Object.entries(MODULE_CATS)){
    if(members.includes(raw)) return cat;
  }
  return "其他";
}
// 所有归类名（固定顺序）
const CAT_ORDER = Object.keys(MODULE_CATS);

function buildBrokerRows(items){
  const map = {};
  for(const it of items){
    const b = it.broker;
    if(b === "证券业") continue;
    if(!map[b]) map[b] = {broker:b, apps:new Set(), modules:new Set(), modCats:new Set(), tags:new Set(), count:0, latest:null, items:[]};
    const r = map[b];
    r.count++;
    r.items.push(it);
    if(it.app && it.app!=="—") r.apps.add(it.app);
    if(it.module){
      r.modules.add(it.module);
      r.modCats.add(moduleCat(it.module));
    }
    (it.tags||[]).forEach(t=>r.tags.add(t));
    if(!r.latest || (it.publishedAt||"") > (r.latest.publishedAt||"")) r.latest = it;
  }
  const rows = Object.values(map).map(r=>{
    // 构建战略看点：综合产品特色、版本能力、差异化亮点
    const parts = [];
    // 产品线
    if(r.apps.size) parts.push([...r.apps].join("·"));
    // 核心标签（取最有代表性的前5个）
    const topTags = [...r.tags].slice(0,5);
    if(topTags.length) parts.push(topTags.join("、"));
    // 覆盖能力域
    if(r.modCats.size) parts.push(`覆盖${[...r.modCats].join("、")}`);
    // 最新动态摘要
    if(r.latest){
      const summary = (r.latest.summary||r.latest.title).replace(/[|]/g,"，");
      if(summary) parts.push(`最新：${summary.slice(0,60)}${summary.length>60?"…":""}`);
    }
    return {
      broker:r.broker, apps:[...r.apps], modules:[...r.modules], modCats:[...r.modCats],
      tags:[...r.tags], count:r.count, latest:r.latest, items:r.items,
      note: parts.join("；")
    };
  });
  rows.sort((a,b)=> b.count - a.count);
  return rows;
}

async function initMatrix(){
  const {meta, items} = await loadData();
  const rows = buildBrokerRows(items);

  // 使用归类后的能力域（而非原始零散模块）
  const catSet = new Set(); rows.forEach(r=>r.modCats.forEach(c=>catSet.add(c)));
  const categories = CAT_ORDER.filter(c=>catSet.has(c));

  document.getElementById("mBrokers").textContent = rows.length;
  document.getElementById("mMods").textContent = categories.length;
  document.getElementById("mTotal").textContent = items.length;

  // 能力域覆盖条形（按归类后的大类展示）
  const cover = categories.map(cat=>{
    const members = MODULE_CATS[cat] || [];
    // 该能力域下有任意原始模块的券商数
    const n = rows.filter(r=>{
      return r.modules.some(m => members.includes(m) || moduleCat(m) === cat);
    }).length;
    return {m: cat, n};
  }).sort((a,b)=> b.n - a.n);
  const maxN = cover.length ? cover[0].n : 1;
  document.getElementById("modBars").innerHTML = cover.map(c=>
    `<div class="mbar"><span class="ml" title="${esc(c.m)}">${esc(c.m)}</span><div class="mt"><div class="mf" style="width:${Math.round(c.n/maxN*100)}%"></div></div><span class="mn">${c.n}</span></div>`
  ).join("");

  // 能力域筛选标签（可折叠）
  const COLLAPSE_SHOW = 6;
  const modChips = document.getElementById("modChips");
  const modToggle = document.getElementById("modToggle");
  const modCountEl = document.getElementById("modCount");
  let expanded = false;

  function renderChips(){
    const visible = expanded ? categories : categories.slice(0, COLLAPSE_SHOW);
    modCountEl.textContent = `(共 ${categories.length} 个能力域)`;
    modChips.innerHTML = `<button class="mod-chip active" data-val="">全部能力域</button>` +
      visible.map(c=>`<button class="mod-chip" data-val="${esc(c)}">${esc(c)}</button>`).join("");
    if(categories.length > COLLAPSE_SHOW){
      modToggle.style.display = "block";
      modToggle.textContent = expanded ? "收起 ▴" : `展开剩余 ${categories.length - COLLAPSE_SHOW} 个 ▾`;
    } else {
      modToggle.style.display = "none";
    }
    const activeChip = modChips.querySelector(`[data-val="${esc(currentCat)}"]`);
    if(activeChip){
      modChips.querySelectorAll(".mod-chip").forEach(c=>c.classList.remove("active"));
      activeChip.classList.add("active");
    }
  }

  let currentCat = "";
  const wrap = document.getElementById("matrixWrap");
  const search = document.getElementById("search");
  const detailLink = id => `detail.html?id=${encodeURIComponent(id)}`;

  renderChips();

  modToggle.addEventListener("click", ()=>{ expanded = !expanded; renderChips(); });

  modChips.addEventListener("click", e=>{
    const chip = e.target.closest(".mod-chip");
    if(!chip) return;
    modChips.querySelectorAll(".mod-chip").forEach(c=>c.classList.remove("active"));
    chip.classList.add("active");
    currentCat = chip.dataset.val;
    render();
  });

  function renderItemsList(brokerRow){
    /* 渲染某券商的动态列表（用于点击徽章弹出） */
    const lis = brokerRow.items.map(it=>{
      const ti = typeInfo(it.type);
      return `<div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--line);align-items:flex-start">
        <span class="tag type ${ti.cls}" style="flex-shrink:0;margin-top:2px">${ti.label}</span>
        <div style="min-width:0;flex:1">
          <a href="${detailLink(it.id)}" style="font-weight:600;font-size:13px;color:var(--blue);line-height:1.4">${esc(it.title)}</a>
          <div style="font-size:11.5px;color:var(--muted);margin-top:2px">${beijing(it.publishedAt)}${it.module?` · ${esc(it.module)}`:""}</div>
        </div>
      </div>`;
    }).join("");
    return `<div style="padding:12px 16px">${lis}</div>`;
  }

  function render(){
    const c = currentCat;
    const q = search.value.trim().toLowerCase();
    let list = rows.filter(r=> !c || r.modCats.includes(c));
    if(q) list = list.filter(r =>
      (r.broker + r.apps.join("") + r.modules.join("") + r.tags.join("") + r.note).toLowerCase().includes(q));

    if(!list.length){
      wrap.innerHTML = `<div class="empty">没有匹配的券商</div>`;
      document.getElementById("mCnt").textContent = "0";
      return;
    }

    wrap.innerHTML = list.map((r, idx)=>{
      const latest = r.latest;
      return `<div class="broker-card" data-broker-idx="${idx}">
        <div class="bc-header">
          <span class="bc-name">${esc(r.broker)}</span>
          <span class="bc-count bc-count-clickable" title="点击查看全部 ${r.count} 条动态">${r.count} 条 AI 动态</span>
        </div>
        <div class="bc-body">
          <div class="bc-field">
            <span class="fk">代表产品</span>
            <div class="fv">${r.apps.length ? r.apps.map(a=>`<span class="chip-soft">${esc(a)}</span>`).join("") : '<span class="muted">—</span>'}</div>
          </div>
          <div class="bc-field">
            <span class="fk">覆盖能力域</span>
            <div class="fv">${r.modCats.map(c=>`<span class="chip-soft" style="border-color:var(--blue);color:var(--blue);font-weight:700">${esc(c)}</span>`).join("")}</div>
          </div>
          <div class="bc-field">
            <span class="fk">核心能力标签</span>
            <div class="fv">${r.tags.length ? r.tags.slice(0,10).map(t=>`<span class="tag-chip">${esc(t)}</span>`).join("") : '<span class="muted">—</span>'}</div>
          </div>
          <div class="bc-field" style="min-width:260px">
            <span class="fk">最新动态</span>
            <div class="fv bc-latest">
              <a href="${detailLink(latest.id)}">${esc(latest.title)}</a>
              <span style="font-size:11.5px;color:var(--muted)">${beijing(latest.publishedAt)}</span>
            </div>
          </div>
        </div>
        <div class="bc-note"><strong>产品特色：</strong>${esc(r.note)}</div>
        <!-- 点击展开的动态列表（默认隐藏） -->
        <div class="bc-items-panel" id="bip-${idx}" style="display:none"></div>
      </div>`;
    }).join("");
    document.getElementById("mCnt").textContent = list.length;

    // 绑定点击事件：AI动态徽章 → 展开/收起该券商的完整动态列表
    wrap.querySelectorAll(".bc-count-clickable").forEach(badge=>{
      badge.addEventListener("click", ()=>{
        const card = badge.closest(".broker-card");
        const idx = card.dataset.brokerIdx;
        const panel = document.getElementById(`bip-${idx}`);
        const brokerData = list.find((_,i)=>String(i)===idx);
        if(!panel || !brokerData) return;
        if(panel.style.display==="none"){
          panel.innerHTML = renderItemsList(brokerData);
          panel.style.display = "block";
          badge.textContent = "收起动态 ▴";
        } else {
          panel.style.display = "none";
          badge.textContent = `${brokerData.count} 条 AI 动态`;
        }
      });
    });
  }
  search.addEventListener("input", render);
  render();
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if(page==="index") initIndex();
  else if(page==="archive") initArchive();
  else if(page==="detail") initDetail();
  else if(page==="matrix") initMatrix();
});
