# -*- coding: utf-8 -*-
"""
一次性迁移：把统一压在建库日的 date 字段，重排为各自的真实发布日期。

背景：建库时 20 条真实动态的 date 全部写成 2026-08-11（建库日），
但它们的 publishedAt 横跨 2025-03 → 2026-07，导致归档页只有一天。

本脚本落实三条已确认的数据规则：
  1. date          = publishedAt 的日期（归档维度，真实发生日）
  2. firstSeenDate = 首次被采集发现的日期（发现维度，驱动首页「今日新发现」）
  3. backfill      = publishedAt 距 firstSeenDate 超过 FRESH_DAYS 天 → 补录条目
     timeInferred  = 发布时间不可解析、以发现日推断 → 界面需明确标注

为什么要拆 date 与 firstSeenDate：
  若首页按 date 过滤，则今天新发现的一条「上月发布」的动态永远不会出现在首页；
  若归档按 firstSeenDate 归档，则历史浏览退化成「按我什么时候抓到」而非「何时发生」。
  两个维度各司其职，才能同时满足「每日有新内容」与「历史归档真实」。
"""
import json, os

BASE = "E:/个人文件夹/workbuddy-flies/2026-08-11-09-52-56/site"
DATA = os.path.join(BASE, "data", "data.json")
FRESH_DAYS = 30


def days_between(a, b):
    """a、b 为 YYYY-MM-DD，返回 b-a 的天数。"""
    from datetime import date
    ay, am, ad = map(int, a.split("-"))
    by, bm, bd = map(int, b.split("-"))
    return (date(by, bm, bd) - date(ay, am, ad)).days


def main():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)

    items = d["items"]
    meta = d.get("meta", {})

    changed = 0
    for it in items:
        pub = (it.get("publishedAt") or "")[:10]
        seen = (it.get("collectedAt") or it.get("date") or "")[:10]

        if not pub:
            # 无可解析发布时间：以发现日推断，并打标注
            pub = seen
            it["publishedAt"] = seen + "T09:00:00+08:00"
            it["timeInferred"] = True
        else:
            it["timeInferred"] = False

        it["firstSeenDate"] = seen
        old_date = it.get("date")
        it["date"] = pub
        if old_date != pub:
            changed += 1

        age = days_between(pub, seen) if (pub and seen) else 0
        it["backfill"] = age > FRESH_DAYS
        it["ageDays"] = age

    # 归档维度（真实发生日）
    dates = sorted({i["date"] for i in items if i.get("date")}, reverse=True)
    counts = {}
    for i in items:
        counts[i["date"]] = counts.get(i["date"], 0) + 1

    # 发现维度（驱动首页）
    seen_dates = sorted({i["firstSeenDate"] for i in items if i.get("firstSeenDate")}, reverse=True)
    seen_counts = {}
    for i in items:
        seen_counts[i["firstSeenDate"]] = seen_counts.get(i["firstSeenDate"], 0) + 1

    brokers = []
    for i in items:
        if i.get("broker") and i["broker"] not in brokers:
            brokers.append(i["broker"])

    meta.update({
        "dates": dates,
        "counts": counts,
        "firstSeenDates": seen_dates,
        "firstSeenCounts": seen_counts,
        "brokers": brokers,
        "total": len(items),
        "freshDays": FRESH_DAYS,
        "windowPolicy": "上一交易日 08:30 → 今日 08:30（周一及节后首日自动回溯至上一交易日）",
        "dedupe": "URL 归一化 + 标题指纹（seen.json），仅首次发现计入当日",
    })

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "items": items}, f, ensure_ascii=False, indent=2)

    fresh = sum(1 for i in items if not i["backfill"])
    print(f"[retime] 完成，共 {len(items)} 条，date 变更 {changed} 条")
    print(f"[retime] 归档日期分布（{len(dates)} 天）：{dates}")
    print(f"[retime] 发现日期（{len(seen_dates)} 天）：{seen_dates}")
    print(f"[retime] 新鲜条目 {fresh} 条 / 补录条目 {len(items)-fresh} 条（阈值 {FRESH_DAYS} 天）")
    print(f"[retime] 时间推断条目：{sum(1 for i in items if i.get('timeInferred'))} 条")


if __name__ == "__main__":
    main()
