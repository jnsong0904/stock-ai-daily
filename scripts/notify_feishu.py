# -*- coding: utf-8 -*-
"""
飞书群机器人 webhook 推送（云端用，不依赖 lark-cli）。

用法（GitHub Actions 中）：
  环境变量：
    FEISHU_WEBHOOK        飞书自定义机器人 webhook 地址（必填，否则静默跳过）
    FEISHU_WEBHOOK_SECRET 机器人加签密钥（可选，与机器人配置一致）
    SITE_URL              站点访问地址（可选，写入推送正文）
    SEC_AI_ROOT           项目根目录（可选，默认按本文件位置推导）

读取 site/data/data.json 中当日采集报告，组装 markdown 摘要并 POST 到 webhook。
失败不抛出（通知为附加能力），仅打印错误。
"""
import os, sys, json, time, hashlib, hmac, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

ROOT = os.environ.get("SEC_AI_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "site", "data", "data.json")


def now_bj_iso():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def today_bj():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")


def build_markdown():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    meta = d.get("meta", {})
    items = d.get("items", [])
    today = today_bj()
    today_new = [i for i in items if i.get("firstSeenDate") == today]
    report = (meta.get("collectionReports") or {}).get(today) or {}
    totals = report.get("totals", {})
    sources = report.get("sources", [])

    lines = [f"# 证券业 AI 动态日报 · {today}", ""]
    # 交易日/休市
    is_td = report.get("prevTradingDay") is not None or bool(report)
    lines.append(f"**交易日**：{'是' if report else '休市/无采集记录'}")
    lines.append("")
    lines.append(f"**今日新增 {totals.get('accepted', len(today_new))} 条**"
                 f"（候选 {totals.get('raw', 0)}，重复 {totals.get('duplicated', 0)}）")
    lines.append("")
    if sources:
        lines.append("**各数据源**")
        for s in sources:
            lines.append(f"- {s.get('name','?')}：{s.get('status','?')}，抓取 {s.get('fetched',0)} 条")
        lines.append("")
    lines.append(f"**累计**：库内共 {meta.get('total', len(items))} 条，"
                 f"覆盖 {len(meta.get('dates', []))} 个归档日")
    site_url = os.environ.get("SITE_URL", "").strip()
    if site_url:
        lines.append("")
        lines.append(f"**访问地址**\n{site_url}")
    return "\n".join(lines)


def sign(secret, ts):
    string_to_sign = f"{ts}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return urllib.parse.base64.b64encode(hmac_code).decode("utf-8") if hasattr(urllib.parse, "base64") else __import__("base64").b64encode(hmac_code).decode("utf-8")


def send(webhook, secret, md):
    payload = {"msg_type": "interactive", "card": {
        "elements": [{"tag": "markdown", "content": md}],
        "header": {"title": {"tag": "plain_text", "content": "证券业 AI 动态日报"}},
    }}
    if secret:
        ts = str(int(time.time()))
        payload["timestamp"] = ts
        payload["sign"] = sign(secret, ts)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def main():
    webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        print("[notify] 未配置 FEISHU_WEBHOOK，跳过飞书推送。")
        return 0
    secret = os.environ.get("FEISHU_WEBHOOK_SECRET", "").strip()
    try:
        md = build_markdown()
        resp = send(webhook, secret, md)
        ok = (resp.get("StatusCode") == 0 or resp.get("code") == 0 or resp.get("status") == 0)
        print(f"[notify] 飞书推送 {'成功' if ok else '返回异常'}：{resp}")
        return 0 if ok else 1
    except Exception as e:
        print(f"[notify] 飞书推送失败：{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
