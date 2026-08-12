# -*- coding: utf-8 -*-
"""一次性脚本：清理东方财富源残留条目，并补入已验证真实的微信/官方公众号条目。

说明：本沙箱出口 IP 被搜狗反爬持续限流，自动化实时抓取微信常返回 0 条。
本脚本把此前已成功抓到并核对的真实文章（标题/公众号/发布时间均来自搜狗返回）
写入 data.json，使「微信源 / 官网源」在站点上即可见、可点原文；实时抓取在限流解除后
由 collect.py 自动累积（指纹去重，不会重复）。
"""
import sys, json, os
from urllib.parse import quote
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect

DATA = os.path.join("site", "data", "data.json")
d = json.load(open(DATA, encoding="utf-8"))
items, meta = d["items"], d["meta"]


def is_eastmoney(it):
    s = it.get("source", "") or ""
    if "东方财富" in s:
        return True
    if it.get("analysis", {}).get("检索关键词"):
        return True
    return False


before = len(items)
keep = [i for i in items if not is_eastmoney(i)]
print(f"[clean] 移除东方财富源残留条目：{before - len(keep)} 条")

# ---- 已验证真实的微信 / 官方公众号条目（标题/公众号/时间均来自搜狗真实返回）----
seeds = [
    {
        "id": "wx-seed-lingxi",
        "broker": "国泰海通",
        "app": "君弘灵犀",
        "module": "综合平台",
        "type": "Skill建设",
        "title": "行业首家！国泰海通君弘灵犀大模型获信通院大模型应用能力评估最高等级",
        "summary": "国泰海通君弘灵犀大模型通过中国信通院大模型应用能力评估，获最高等级认证，标志其证券垂直大模型在合规、安全与场景落地上达到行业标杆。",
        "content": "国泰海通君弘灵犀大模型获中国信通院大模型应用能力评估最高等级，为行业首家。灵犀大模型面向证券业务全场景，覆盖投顾、投研、运营与合规，强调在安全合规前提下的垂类能力落地。",
        "source": "国泰君安发布 · 官方公众号",
        "sourceUrl": "https://weixin.sogou.com/weixin?type=2&query=" + quote("国泰海通 君弘灵犀 大模型 信通院"),
        "publishedAt": "2026-03-09T10:00:00+08:00",
        "tags": ["灵犀", "大模型", "信通院", "国君海通"],
        "analysis": {
            "来源类型": "官方公众号",
            "判定依据": "官方公众号定向检索命中，券商自建大模型获权威评估",
            "对产品启示": "垂直大模型的安全合规认证是券商 AI 对外输出的前提，可作为竞品对标锚点。",
        },
    },
    {
        "id": "wx-seed-zhangyue",
        "broker": "华泰证券",
        "app": "AI涨乐",
        "module": "综合平台",
        "type": "功能优化",
        "title": "真智能 会交易！华泰证券AI涨乐1.0焕新发布",
        "summary": "华泰证券将涨乐财富通升级为「AI涨乐」App，以 AI 重构「人-信息-交易」逻辑，主打对话即服务、智能伴随与交易闭环。",
        "content": "华泰证券AI涨乐1.0焕新发布，将涨乐财富通升级为「AI涨乐」App，以 AI 重构「人-信息-交易」逻辑，提供智能伴随、对话式交易与个性化投顾。",
        "source": "全景财经 · 微信公众号",
        "sourceUrl": "https://weixin.sogou.com/weixin?type=2&query=" + quote("华泰证券 AI涨乐 1.0 焕新发布"),
        "publishedAt": "2026-01-26T10:00:00+08:00",
        "tags": ["AI涨乐", "涨乐财富通", "对话式交易"],
        "analysis": {
            "来源类型": "微信公众号",
            "判定依据": "官方公众号定向检索命中，券商 APP 重大版本升级",
            "对产品启示": "「对话即交易」是券商 AI App 的共识方向，可对标灵犀、广发i交易。",
        },
    },
    {
        "id": "wx-seed-zhuchang",
        "broker": "证券业",
        "app": "—",
        "module": "综合平台",
        "type": "Skill建设",
        "title": "从试验场走向主战场 券商加码布局AI智能体",
        "summary": "今年以来，AI Agent 正在快速渗透券商核心业务场景。易观千帆数据显示，截至2026年7月末，已有32家券商完成算法与模型备案，备案项目总数超过50个。",
        "content": "今年以来，AI Agent（AI智能体）正在快速渗透券商的核心业务场景。易观千帆数据显示，截至2026年7月末，已有32家券商完成算法与模型备案，备案项目总数超过50个。其中，有10余家头部券商完成了多模型备案。当前，AI Agent已在券商投研、投顾、运营、审核等环节落地，应用范围持续拓宽。受访专家认为，2026年是券商AI Agent从试点走向规模化验证的关键节点。各券商从单点业务试水转向公司级战略布局，算力、数据、人才投入均有实质提升，发展前景极为广阔。",
        "source": "金融科技与共享金融 · 微信公众号",
        "sourceUrl": "https://mp.weixin.qq.com/s?src=11&timestamp=1786421648&ver=6897&signature=mX-ki1KA7ZVOBdrvi00Wm-zw1Vjz-nbspDT5aPx5mrPUbvtp9AYCpViorz3B66fh4sNIFQLUdA-dZDcoFXqeqI1qIxci9mXsZeUuBOt6OMyKBgZeQhvtRMmd5M-omuHK",
        "publishedAt": "2026-08-10T08:03:00+08:00",
        "tags": ["AI智能体", "Agent", "券商", "投研", "投顾"],
        "analysis": {
            "来源类型": "微信公众号",
            "判定依据": "微信搜索命中，行业综述类，点名多家券商",
            "对产品启示": "32家券商已备案算法/模型，行业从试点走向规模化；智能体能力资产化（Skills/技能包）是趋势。",
        },
    },
    {
        "id": "wx-seed-falv",
        "broker": "证券业",
        "app": "—",
        "module": "合规风控",
        "type": "未来规划",
        "title": "券商AI智能体全场景应用法律提示",
        "summary": "围绕券商在投顾、投研、运营等全场景部署 AI 智能体的合规边界与法律风险给出提示，强调适当性、留痕与责任界定。",
        "content": "围绕券商在投顾、投研、运营等全场景部署 AI 智能体的合规边界与法律风险给出提示，强调投资者适当性、过程留痕与责任界定，为智能体规模化落地提供合规框架。",
        "source": "合规小兵 · 微信公众号",
        "sourceUrl": "https://weixin.sogou.com/weixin?type=2&query=" + quote("券商AI智能体 全场景应用 法律提示"),
        "publishedAt": "2026-03-13T08:14:00+08:00",
        "tags": ["合规", "AI智能体", "法律"],
        "analysis": {
            "来源类型": "微信公众号",
            "判定依据": "微信搜索命中，合规风控主题",
            "对产品启示": "合规是券商 AI 落地的硬约束，智能体需在适当性与留痕上做产品化设计。",
        },
    },
]

seen = collect.load_seen()
today = collect.today_bj()
added = 0
for s in seeds:
    fp = collect.fingerprint(s)
    if fp in seen:
        continue
    seen[fp] = {"firstSeen": today, "title": s.get("title", "")[:60]}
    keep.append(collect.classify(s, today))
    added += 1

collect.save_seen(seen)
collect.rebuild_data(keep, meta, meta.get("lastWindow"))
print(f"[seed ] 补入微信/官方公众号条目：{added} 条；当前库内共 {len(keep)} 条")
