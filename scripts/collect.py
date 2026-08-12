# -*- coding: utf-8 -*-
"""
证券业 AI 动态日报 —— 采集管线（双闸门时间窗口版）

时间窗口规则（本文件是该规则的唯一权威实现）：

  窗口边界    since = 上一个交易日 08:30，until = 今日 08:30（北京时间）
              周二~周五 → 24 小时
              周一      → 72 小时（自动覆盖周末）
              节后首日  → 自动回溯至节前最后一个交易日，覆盖整个假期
              非交易日  → 不采集，标注休市，数据原样保留

  闸门一 去重  URL 归一化 + 标题指纹 → seen.json 指纹库
              只有指纹库中不存在的条目才算「新发现」，与对方是否提供时间戳无关。
              这是「新」的真正定义，防止同一条动态被多个源重复报道时反复入库。

  闸门二 新鲜度 通过闸门一后按 publishedAt 判定：
              距今 ≤ FRESH_DAYS(30) 天 → 正常条目
              距今 >  FRESH_DAYS 天    → backfill=True（补录），可检索但不占当日头条
              无可解析时间             → 以发现日推断 + timeInferred=True，界面明确标注

  双日期维度  date          = publishedAt 日期 → 归档页按真实发生日浏览
              firstSeenDate = 首次发现日期     → 首页「今日新发现」
              二者分离，兼顾「每天有新内容」与「历史归档真实」。

安全约束：data.json 是真相源。任何一次运行都不会清空它，也不会把 demo 翻回 True。
"""
import json, os, re, sys, hashlib
from datetime import datetime, timezone, timedelta, date as _date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parsers

# 自动推导项目根目录（collect.py 位于 <ROOT>/scripts/ 下），换机器/移动文件夹也能跑。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(BASE, "data")
# 源配置路径：可用环境变量 SEC_AI_SOURCES 覆盖（云端用 scripts/sources.cloud.json）。
# 支持绝对路径或相对 ROOT 的路径；未设置时默认 scripts/sources.json（本地 WorkBuddy 流程）。
SOURCES = os.environ.get("SEC_AI_SOURCES") or os.path.join(ROOT, "scripts", "sources.json")
if not os.path.isabs(SOURCES):
    SOURCES = os.path.join(ROOT, SOURCES)
SEEN_DB = os.path.join(ROOT, "scripts", "seen.json")

RUN_TIME = "08:30"      # 自动化触发时刻，窗口以此对齐
FRESH_DAYS = 30         # 闸门二：新鲜度上限
MAX_LOOKBACK = 15       # 回溯上一交易日的最大天数（覆盖最长假期）

# 2026 A股休市（上交所/深交所/北交所 2025-12-22 发布），仅列非周末的休市工作日
# 周末由 is_trading_day 的 weekday()<5 自动排除，无需重复列出
HOLIDAYS_2026 = set([
    "2026-01-01","2026-01-02",                       # 元旦 1/1-1/3(含周末)
    "2026-02-16","2026-02-17","2026-02-18","2026-02-19","2026-02-20","2026-02-23",  # 春节 2/15-2/23
    "2026-04-06",                                    # 清明 4/4-4/6(含周末)
    "2026-05-01","2026-05-04","2026-05-05",          # 劳动 5/1-5/5(含周末)
    "2026-06-19",                                    # 端午 6/19-6/21(含周末)
    "2026-09-25",                                    # 中秋 9/25-9/27(含周末)
    "2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07",  # 国庆 10/1-10/7(含周末)
])


# ---------- 时间基础设施 ----------

def today_bj():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")


def now_bj_iso():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def is_trading_day(d):
    dt = datetime.strptime(d, "%Y-%m-%d")
    return dt.weekday() < 5 and d not in HOLIDAYS_2026


def prev_trading_day(d):
    """回溯上一个交易日；跨周末与长假自动延展。"""
    dt = datetime.strptime(d, "%Y-%m-%d")
    for _ in range(MAX_LOOKBACK):
        dt -= timedelta(days=1)
        s = dt.strftime("%Y-%m-%d")
        if is_trading_day(s):
            return s
    return None


def collection_window(today):
    """返回 (since_iso, until_iso, span_hours, prev_day)。"""
    prev = prev_trading_day(today)
    if not prev:
        prev = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    since = f"{prev}T{RUN_TIME}:00+08:00"
    until = f"{today}T{RUN_TIME}:00+08:00"
    span = int((datetime.fromisoformat(until) - datetime.fromisoformat(since)).total_seconds() // 3600)
    return since, until, span, prev


def days_between(a, b):
    ay, am, ad = map(int, a.split("-"))
    by, bm, bd = map(int, b.split("-"))
    return (_date(by, bm, bd) - _date(ay, am, ad)).days


# ---------- 闸门一：指纹去重 ----------

def normalize_url(u):
    if not u:
        return ""
    u = u.strip().split("#")[0]
    u = re.sub(r"[?&](utm_[^=]+|from|spm|share_[^=]+)=[^&]*", "", u)
    u = re.sub(r"[?&]$", "", u)
    return u.rstrip("/").lower()


def fingerprint(item):
    """URL 归一化 + 标题去空白，联合哈希。任一相同即视为同一条动态。"""
    url = normalize_url(item.get("sourceUrl", ""))
    title = re.sub(r"\s+", "", item.get("title", ""))
    return hashlib.sha1(f"{url}|{title}".encode("utf-8")).hexdigest()[:16]


# 跨源转载去重：同一文章被多源转载时，标题核心相同、仅末尾追加来源/栏目标签
# （_搜狐网 / |agent|ai / __财经头条__新 / -中国证券协会 / ·快讯 等花样繁多）。
# 用「归一化标题的子串包含」判定：短标题是长标题的子串（且≥12字）即视为同一篇。
def _norm_title_dedup(title):
    return re.sub(r"[\s，。、,；;：:！!?？()（）\[\]【】\"'“”‘’`]+", "", (title or "")).lower()


def load_seen():
    if os.path.exists(SEEN_DB):
        with open(SEEN_DB, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen):
    with open(SEEN_DB, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


# ---------- 闸门二：新鲜度分级 ----------

def classify(item, today):
    """补全时间字段并分级。返回处理后的 item。"""
    pub = (item.get("publishedAt") or "")[:10]
    if not pub:
        item["publishedAt"] = f"{today}T09:00:00+08:00"
        item["timeInferred"] = True
        pub = today
    else:
        item.setdefault("timeInferred", False)

    item["firstSeenDate"] = today
    item["collectedAt"] = now_bj_iso()
    item["date"] = pub
    age = days_between(pub, today)
    item["ageDays"] = age
    item["backfill"] = age > FRESH_DAYS
    return item


# ---------- 采集接入点 ----------

def fetch_source(src, since, until):
    """真实采集接入点 —— 分发到 parsers.py 中对应 type 的解析器。

    注意「窗口」与「新」的分工，这是本管线的核心设计：
      窗口 (since/until) 决定「本次运行覆盖哪段时间」，用于日志与元信息；
      是否「新」则由闸门一的指纹库判定 —— 因为券商 APP 更新日志、
      官网新闻普遍不提供可靠时间戳，只按时间过滤必然漏采。
      指纹库让「新」不依赖对方是否诚实标注时间。

    返回 list[item-dict]，字段：
      broker, app, module, type(功能优化|Skill建设|未来规划), title, summary,
      content, source, sourceUrl, publishedAt, tags, analysis
    """
    return parsers.dispatch(src, since, until)


# ---------- 数据重建 ----------

def load_base():
    path = os.path.join(DATA_DIR, "data.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("items", []), d.get("meta", {})
    return [], {}


def rebuild_data(items, base_meta, window_info=None):
    brokers = []
    for i in items:
        if i.get("broker") and i["broker"] not in brokers:
            brokers.append(i["broker"])

    dates = sorted({i.get("date") for i in items if i.get("date")}, reverse=True)
    counts = {}
    for i in items:
        if i.get("date"):
            counts[i["date"]] = counts.get(i["date"], 0) + 1

    seen_dates = sorted({i.get("firstSeenDate") for i in items if i.get("firstSeenDate")}, reverse=True)
    seen_counts = {}
    for i in items:
        if i.get("firstSeenDate"):
            seen_counts[i["firstSeenDate"]] = seen_counts.get(i["firstSeenDate"], 0) + 1

    # 动态类型：以数据中实际出现的类型为准，按固定优先级排序，
    # 保证「今日 / 历史归档」两页的分类完全一致，且不遗漏（如法律合规、产品功能）。
    TYPE_ORDER = ["产品功能", "Skill建设", "未来规划", "法律合规"]
    present_types = sorted({i.get("type") for i in items if i.get("type")})
    types = [t for t in TYPE_ORDER if t in present_types] + \
            [t for t in present_types if t not in TYPE_ORDER]

    meta = dict(base_meta)
    meta.update({
        "demo": base_meta.get("demo", False),
        "generatedAt": now_bj_iso(),
        "timezone": "Asia/Shanghai",
        "dates": dates,
        "counts": counts,
        "firstSeenDates": seen_dates,
        "firstSeenCounts": seen_counts,
        "total": len(items),
        "brokers": brokers,
        "types": types,
        "freshDays": FRESH_DAYS,
    })
    if window_info:
        meta["lastWindow"] = window_info

    with open(os.path.join(DATA_DIR, "data.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "items": items}, f, ensure_ascii=False, indent=2)
    return len(items), dates


# ---------- 主流程 ----------

def main():
    today = today_bj()
    print(f"[collect] 运行日期（北京时间）：{today}")

    if not is_trading_day(today):
        print("[collect] 非交易日（休市）：跳过采集，数据原样保留。")
        return

    since, until, span, prev = collection_window(today)
    print(f"[collect] 采集窗口：{since[:16]} → {until[:16]}（{span} 小时，上一交易日 {prev}）")

    import parsers as _P
    _P.print_proxy_status()

    base_items, base_meta = load_base()
    seen = load_seen()
    print(f"[collect] 指纹库已有 {len(seen)} 条历史记录")

    src_cfg = {"sources": []}
    if os.path.exists(SOURCES):
        with open(SOURCES, encoding="utf-8") as f:
            src_cfg = json.load(f)

    raw = []
    sources_report = []
    for s in src_cfg.get("sources", []):
        if not s.get("enabled", True):
            continue
        stype = s.get("type")
        name = s.get("name", stype)
        channel = {"appstore": "App Store", "websearch_raw": "全网新闻"}.get(stype, stype)
        print(f"[collect] 采集源：{name}（{stype}）")
        items = fetch_source(s, since, until)
        raw.extend(items)
        rep = parsers._LAST_SOURCE_STATUS.get(stype, {})
        sources_report.append({
            "name": name,
            "channel": channel,
            "status": rep.get("status", "success" if items else "empty"),
            "error": rep.get("error", ""),
            "fetched": rep.get("fetched", len(items)),
            "queryCount": rep.get("queryCount"),
            "candidates": rep.get("candidates"),
            "note": rep.get("note", ""),
        })

    # 闸门一：指纹去重（URL+标题指纹 + 跨源转载子串去重）
    fresh_items, dup = [], 0
    # 跨源去重要和已入库的 base 标题比对，否则同篇文章换个来源又会被当作新条目入库
    accepted_titles = [t for t in (_norm_title_dedup(i.get("title", "")) for i in base_items)
                       if t and len(t) >= 12]
    for it in raw:
        fp = fingerprint(it)
        if fp in seen:
            dup += 1
            continue
        nt = _norm_title_dedup(it.get("title", ""))
        is_cross_dup = False
        if nt and len(nt) >= 12:
            for at in accepted_titles:
                # 短标题是长标题的子串（或反之）→ 同一文章跨源转载
                if (nt in at) or (at in nt):
                    is_cross_dup = True
                    break
        if is_cross_dup:
            dup += 1
            continue
        if nt:
            accepted_titles.append(nt)
        seen[fp] = {"firstSeen": today, "title": it.get("title", "")[:60]}
        it["fp"] = fp
        fresh_items.append(it)

    # 闸门二：新鲜度分级
    fresh_items = [classify(it, today) for it in fresh_items]
    backfilled = sum(1 for i in fresh_items if i.get("backfill"))
    inferred = sum(1 for i in fresh_items if i.get("timeInferred"))

    window_info = {
        "since": since, "until": until, "spanHours": span,
        "prevTradingDay": prev, "runAt": now_bj_iso(),
        "raw": len(raw), "duplicated": dup,
        "accepted": len(fresh_items), "backfill": backfilled, "timeInferred": inferred,
    }
    # 采集窗口报告：按运行日（= 新发现日）记录每个数据源的成功/失败与抓取数量
    collect_report = {
        "since": since, "until": until, "spanHours": span,
        "prevTradingDay": prev, "runAt": now_bj_iso(),
        "sources": sources_report,
        "totals": {
            "raw": len(raw), "duplicated": dup,
            "accepted": len(fresh_items), "backfill": backfilled, "timeInferred": inferred,
        },
    }
    base_meta.setdefault("collectionReports", {})
    base_meta["collectionReports"][today] = collect_report

    if fresh_items:
        by_id = {i.get("id"): i for i in base_items if i.get("id")}
        for it in fresh_items:
            by_id[it.get("id") or it["fp"]] = it
        merged = list(by_id.values())

        with open(os.path.join(DATA_DIR, f"daily_{today}.json"), "w", encoding="utf-8") as f:
            json.dump({"date": today, "window": window_info, "items": fresh_items},
                      f, ensure_ascii=False, indent=2)

        base_meta["demo"] = False
        total, dates = rebuild_data(merged, base_meta, window_info)
        save_seen(seen)
        print(f"[collect] 窗口内抓取 {len(raw)} 条 → 去重后新增 {len(fresh_items)} 条"
              f"（重复 {dup}，补录 {backfilled}，时间推断 {inferred}）")
        print(f"[collect] 合并完成，库内共 {total} 条，覆盖 {len(dates)} 个归档日")
    else:
        print(f"[collect] 窗口内无新发现（抓取 {len(raw)}，重复 {dup}）；data.json 原样保留。")
        if base_items:
            rebuild_data(base_items, base_meta, window_info)
        save_seen(seen)


if __name__ == "__main__":
    main()
