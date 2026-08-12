# -*- coding: utf-8 -*-
"""
证券业 AI 动态日报 —— 真实数据源解析器

已实现三个源：

  appstore          Apple iTunes Lookup API（官方结构化接口）
                    拉取券商 APP 最新版本的更新日志，过滤出含 AI 能力描述的版本。
                    对应需求第一类：券商 APP 中 AI 功能的迭代优化。

  eastmoney_search  【已停用】东方财富资讯搜索 API。用户反馈其结果偏「券商研究 AI 行业」
                    的投资观点，非「券商自己建 AI」的动态，故在 sources.json 中禁用，
                    由下面的微信源替代。

  sogou_wechat      搜狗微信搜索（type=sogou_wechat，单一解析器服务两类需求）
                    ① 全网 + 微信公众号行业资讯（keywords 泛关键词）—— 需求替代源；
                    ② 官方源（official=true + queries 带 broker 定向检索）—— 逐家券商
                       官方公众号，是「官网源」的可行替代（券商官网多为 SPA/404）。
                    对应需求第二、三类：Skill/智能体能力建设、未来 AI 规划与战略。

信噪比控制是本文件的核心。券商领域最大的干扰项不是无关新闻，而是
「XX证券：AI硬件品种缩圈」这类研报观点 —— 它同时包含券商名和 AI 词，
朴素关键词匹配必然误收。三层过滤专门针对这一点设计。
"""
import os, json, re, ssl, time, hashlib, http.cookiejar, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

# SOCKS5/SOCKS4 代理需要 PySocks。未安装时优雅降级（该请求走直连并提示），
# 不影响 http/https 代理与直连逻辑。
try:
    import socks
    _HAVE_SOCKS = True
except Exception:
    socks = None
    _HAVE_SOCKS = False


def _parse_socks(proxy_url):
    """socks5://[user:pass@]host:port → (version, host, port, user, pwd)。"""
    m = re.match(r"socks([45])://(?:([^:@]+):([^@]+)@)?([^:]+):(\d+)", proxy_url)
    if not m:
        return None
    return int(m.group(1)), m.group(4), int(m.group(5)), m.group(2), m.group(3)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
# 部分券商官网仍用旧版 TLS 重协商（如国泰海通），不开这个开关会直接握手失败
try:
    _CTX.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
except Exception:
    pass

# 会话级 Cookie —— 搜狗的跳转链接还原强依赖 SNUID/SUID，
# 无 Cookie 时 /link 页面不会吐出真实地址（实测只返回空跳转壳）。
_CJ = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_CJ),
    urllib.request.HTTPSHandler(context=_CTX),
)

# ============================================================
#  代理轮换（解决沙箱共享出口 IP 被搜狗/必应限流）
# ============================================================
# 配置方式（任选其一，未配置则直连，行为不变）：
#   1) 环境变量：  export SEC_AI_PROXIES="http://1.2.3.4:8080,http://5.6.7.8:8080"
#   2) 文件：      scripts/proxies.json  →  {"proxies": ["http://1.2.3.4:8080", ...]}
# 支持 http / https 代理（带鉴权：http://user:pass@host:port）。
# 也支持 SOCKS5/SOCKS4 代理（socks5://[user:pass@]host:port），需先 pip install PySocks；
# 未安装时该请求自动降级为直连并提示，不影响其他请求。
def _load_proxies():
    proxies = []
    env = os.environ.get("SEC_AI_PROXIES", "")
    if env:
        proxies += [p.strip() for p in env.split(",") if p.strip()]
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxies.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
            proxies += list(data.get("proxies", []))
    except Exception:
        pass
    # 去重保序
    seen, uniq = set(), []
    for p in proxies:
        if p not in seen:
            seen.add(p); uniq.append(p)
    return uniq

class ProxyRotator:
    """环形代理池。next() 依次取下一个；无代理时返回 None（直连）。"""
    def __init__(self, proxies):
        self.proxies = list(proxies)
        self.idx = 0
    def __bool__(self):
        return bool(self.proxies)
    def next(self):
        if not self.proxies:
            return None
        p = self.proxies[self.idx % len(self.proxies)]
        self.idx += 1
        return p
    def get(self, i=0):
        return self.proxies[i % len(self.proxies)] if self.proxies else None

_PROXIES = _load_proxies()
_ROTATOR = ProxyRotator(_PROXIES)

# 每个解析器运行后回填本字典，供 collect.py 生成「采集窗口」中每源的成功/失败状态。
# 键为 source.type；值为 {"status": "success"|"empty"|"failed", "error": str,
#                         "fetched": int, "queryCount": int?, "candidates": int?, "note": str}
_LAST_SOURCE_STATUS = {}


def _derive_channel(source):
    """由 source 文本推断采集渠道标签（App Store / 微信公众号 / 全网新闻）。"""
    if not source:
        return "全网新闻"
    if "App Store" in source:
        return "App Store"
    if "公众号" in source:
        return "微信公众号"
    return "全网新闻"

def print_proxy_status():
    if _PROXIES:
        print(f"  [info] 已加载 {len(_PROXIES)} 个代理，采集将自动轮换 IP 以规避限流")
    else:
        print("  [warn] 未配置代理（scripts/proxies.json 或 SEC_AI_PROXIES），采集将直连"
              "——沙箱出口 IP 可能被微信/必应限流")


def http_get(url, timeout=25, referer=None, proxy=None):
    """带 Cookie 会话的 GET。可选通过 proxy（http/https 地址）转发以轮换出口 IP。

    url 中的中文/空格统一转义，避免 InvalidURL。
    """
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    url = urllib.parse.quote(url, safe=":/?&=%.,-_~+@*#!$")
    handlers = [urllib.request.HTTPCookieProcessor(_CJ),
                urllib.request.HTTPSHandler(context=_CTX)]
    if proxy:
        if proxy.startswith("socks"):
            if not _HAVE_SOCKS:
                print("  [WARN] 配置了 SOCKS 代理但未安装 PySocks（pip install PySocks），"
                      "本请求走直连")
            else:
                p = _parse_socks(proxy)
                if p:
                    ver, host, port, user, pwd = p
                    stype = socks.PROXY_TYPE_SOCKS5 if ver == 5 else socks.PROXY_TYPE_SOCKS4
                    handlers.insert(0, urllib.request.SOCKSHandler(
                        socks_version=stype, addr=host, port=port,
                        username=user, password=pwd, rdns=True))
                else:
                    print(f"  [WARN] 无法解析 SOCKS 代理地址：{proxy}，本请求走直连")
        else:
            handlers.insert(0, urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def is_antibot(html):
    """判断搜狗是否返回了反爬验证页（触发后需停止请求，否则会越封越死）。"""
    if not html:
        return True
    low = html.lower()
    if "sogou_vr_11002601_box" in html:
        return False
    return any(k in low for k in ["antispider", "antirobot"]) or "请输入" in html or "验证码" in html


def to_bj(iso):
    """把 UTC 时间戳（如 2026-08-10T05:36:41Z）转成北京时间 ISO，避免跨日误判。"""
    if not iso:
        return ""
    try:
        s = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    except Exception:
        return iso


def strip_html(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]*>", "", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    return re.sub(r"[ \t\u3000]+", " ", s).strip()


# ============================================================
#  词表
# ============================================================

# AI 能力词
AI_TERMS = ["AI", "人工智能", "大模型", "智能体", "Agent", "Skill", "数字员工",
            "智能投顾", "投研助手", "DeepSeek", "AIGC", "智能助手", "智能问答",
            "智能诊股", "AI投顾", "机器人", "智投", "智能助理", "AI助手",
            "智能陪伴", "语音助手", "自然语言"]

# 券商 AI 产品品牌名 —— 官方更新日志常只写品牌名，不写「AI」二字
AI_BRANDS = ["灵犀", "妙想", "问财", "文曲星", "天玑", "知己管家", "小安", "小信",
             "慧笔", "智小助", "小方", "东方赢家AI", "海通e海通财AI"]

# App Store 更新日志中「AI」常被误写成「Al」（大写A+小写L）。
# 国泰海通君弘 v9.30.20 原文即为「Al投资助手「灵犀」」，不处理会导致最典型的
# 目标内容被静默丢弃。仅在 Al 后面不接小写字母时替换，避免误伤 Also/Alert/Alpha。
_AL_HOMOGLYPH = re.compile(r"\bAl(?![a-z])")


def normalize_ai_text(s):
    """规范化文本，消除 AI 同形字误写与全角字符带来的漏匹配。"""
    if not s:
        return ""
    s = s.replace("Ａ", "A").replace("Ｉ", "I").replace("ａi", "AI")
    return _AL_HOMOGLYPH.sub("AI", s)

# 券商/证券业实体词
BROKER_TERMS = ["券商", "证券业", "证券公司", "国泰海通", "华泰证券", "华泰", "中信证券",
                "广发证券", "招商证券", "中金公司", "银河证券", "申万宏源", "东方财富",
                "同花顺", "国信证券", "平安证券", "方正证券", "兴业证券", "东方证券",
                "中信建投", "财通证券", "光大证券", "浙商证券", "中泰证券", "国金证券"]

# 研报 / 投资观点类 —— 负向词（这类内容是券商在「研究 AI 行业」，不是「自己建 AI」）
RESEARCH_NOISE = ["晨会", "评级", "目标价", "投资主线", "产业链", "板块", "受益", "估值",
                  "个股", "概念股", "研报", "增持", "买入", "看好", "涨停", "跌停", "ETF",
                  "净利", "业绩预告", "首次覆盖", "维持", "股价", "市值", "盘中", "开盘",
                  "收盘", "主力资金", "北向资金", "涨幅", "跌幅", "持仓", "减持"]

# 自建 / 落地信号 —— 正向词
BUILD_SIGNAL = ["上线", "落地", "发布", "推出", "升级", "迭代", "布局", "接入", "赋能",
                "转型", "建设", "打造", "内测", "公测", "首家", "试点", "展业", "APP",
                "客户端", "规划", "战略", "自研", "部署", "投产", "开放", "重构"]

# 「XX证券：」开头 —— 研报观点的结构性特征，直接否决
RESEARCH_PREFIX = re.compile(r"^[\u4e00-\u9fa5]{2,6}(证券|建投|宏源|海通|财富)\s*[：:]")

# 股票行情/数据页 —— 标题含这些词说明是行情页/数据页，与「券商自建 AI 产品」无关，直接否决
# （典型 badcase：国泰海通(601211)_最新价格_行情_走势图_东方财富网）
STOCK_PAGE_NOISE = ["走势图", "最新价格", "实时行情", "K线", "分时图", "换手率",
                    "市盈率", "市净率", "资金流向", "盘口", "收盘价", "开盘价",
                    "股票行情", "股价查询", "实时报价", "行情中心"]

# 动态类型判定（优先级从高到低：法律合规 > Skill建设 > 未来规划 > 产品功能）
#
# ⚠️ 法律合规收窄标准（用户确认 2026-08-11）：
#   仅当内容涉及「国家法律法规条文」或「算法/模型备案等监管备案动作」时，
#   才归入法律合规。以下情况**不归**法律合规：
#     - 产品获得监管同意/审批/认证 → 产品功能（产品本身的能力/资质）
#     - 提及合规部门/风控/安全措施 → 产品功能（产品的功能特性）
#     - 平台/系统建设中提到"合规" → 产品功能或 Skill建设
#   判断关键：这条动态的核心主题是「法规/备案」本身，还是「某个AI产品/功能」？
#
# 「其他」分类已废弃：无法归入前三类的动态默认归入「产品功能」。
TYPE_RULES = [
    ("法律合规", [
        # 核心保留：仅真正的法规条文 / 监管备案类
        "算法备案", "模型备案", "大模型备案", "算法注册",
        "网信办", "深度合成", "生成式AI服务管理办法",
        # 法律条文与法律责任（文章主体是讲法规的）
        "法律提示", "法律风险", "合规边界", "责任界定",
        # 备案结果通报（行业级汇总，核心话题是备案本身）
        "完成备案", "通过备案",
        # ⚠️ 以下词已移除（曾导致产品功能类被误分）：
        #   移除: 监管同意, 获准, 审批, 行政许可, 合规, 监管,
        #         通过评估, 等级保护, 数据安全, 风险提示, 伦理,
        #         合规要求, 监管规定, 合规评估, 获准, 法律(单独),
        #         安全评估 — 这些都是产品特性描述中的常见修饰词
    ]),
    ("Skill建设", ["智能体", "Agent", "Skill", "数字员工", "多智能体", "工作流",
                   "MCP", "插件", "技能"]),
    ("未来规划", ["规划", "战略", "未来", "蓝图", "五年", "目标", "计划", "布局方向",
                  "年报", "展望", "顶层设计", "路线图"]),
    # 产品功能：产品迭代/版本更新/能力上线（兜底分类，覆盖原「其他」）
    ("产品功能", ["升级", "迭代", "版本", "发布", "上线", "优化", "新功能", "重构",
                  "焕新", "改版", "版本更新", "功能"]),
]

# 产品模块识别
MODULE_RULES = [
    ("投顾服务", ["投顾", "顾问", "陪伴", "理财师"]),
    ("智能投研", ["投研", "研报", "研究", "分析师", "研究员"]),
    ("行情交易", ["行情", "交易", "下单", "选股", "诊股", "盯盘"]),
    ("客户服务", ["客服", "问答", "咨询", "客户服务", "答疑"]),
    ("合规风控", ["合规", "风控", "审计", "监管", "反洗钱"]),
    ("财富管理", ["财富", "资产配置", "基金", "理财"]),
    ("投行业务", ["投行", "承销", "保荐", "并购", "IPO"]),
]


def clean_line(s):
    """清洗更新日志单行：去掉序号与「问句？——」式营销前缀，保留能力描述本身。"""
    s = normalize_ai_text(s or "").strip()
    s = re.sub(r"^\s*\d+\s*[、.．)）]\s*", "", s)          # 去「1、」「2.」
    s = re.sub(r"^【[^】]{1,8}】\s*", "", s)                # 去「【行情】」
    s = re.sub(r"^[^？?]{0,24}[？?]\s*[—–\-]{1,2}\s*", "", s)  # 去「机会难捕捉？——」
    return s.strip(" ，。;；")


def _hit(text, words):
    t = normalize_ai_text(text)
    return [w for w in words if w in t]


def hit_ai(text):
    """命中的 AI 能力词 + 券商 AI 产品品牌名（已做同形字规范化）。"""
    return _hit(text, AI_TERMS) + _hit(text, AI_BRANDS)


def guess_type(text):
    for label, kws in TYPE_RULES:
        if any(k in text for k in kws):
            return label
    # 兜底：无法归入法律合规/Skill建设/未来规划的动态，统一归入「产品功能」
    return "产品功能"


def guess_module(text):
    for label, kws in MODULE_RULES:
        if any(k in text for k in kws):
            return label
    return "综合平台"


def guess_broker(title, body=""):
    """判定动态归属的机构。

    行业综述类文章会点名十几家券商，若简单取「正文中最先出现的券商名」，
    会把《证券业扎堆布局AI Skills》这类全行业报道错误挂到某一家名下 ——
    对竞品调研而言这是实质性的信息污染。

    判定顺序：标题点名 > 正文单一机构 > 正文压倒性主导 > 归为「证券业」。
    """
    specific = [b for b in BROKER_TERMS if b not in ("券商", "证券业", "证券公司")]

    def canon(n):
        return "华泰证券" if n == "华泰" else n

    # 一、标题点名的机构最可信
    in_title = sorted((title.index(b), b) for b in specific if b in title)
    if in_title:
        return canon(in_title[0][1])

    # 二、正文频次统计
    counts = {}
    for b in specific:
        c = body.count(b)
        if c:
            counts[canon(b)] = counts.get(canon(b), 0) + c
    if not counts:
        return "证券业"
    if len(counts) == 1:
        return next(iter(counts))

    ranked = sorted(counts.items(), key=lambda x: -x[1])
    # 三、只有压倒性主导（≥3 倍于第二名）才归属单一机构，否则视为行业综述
    if ranked[0][1] >= 3 * ranked[1][1]:
        return ranked[0][0]
    return "证券业"


# ============================================================
#  源一：App Store 版本更新日志
# ============================================================

def parse_appstore(src, since, until):
    """券商 APP 版本更新日志。

    只保留更新说明中含 AI 能力描述的版本 —— 纯 Bug 修复类更新对竞品调研无价值。
    是否「新」由 collect.py 的指纹库判定（指纹含版本号），
    因此同一版本不会重复入库，新版本一出现即被捕获。
    """
    apps = src.get("apps", [])
    if not apps:
        return []

    ids = ",".join(str(a["id"]) for a in apps)
    meta_by_id = {str(a["id"]): a for a in apps}
    url = f"https://itunes.apple.com/lookup?id={ids}&country=cn"

    try:
        data = json.loads(http_get(url))
    except Exception as e:
        print(f"  [ERR ] appstore 请求失败：{type(e).__name__}: {e}")
        _LAST_SOURCE_STATUS["appstore"] = {"status": "failed", "error": f"{type(e).__name__}: {e}",
                                           "fetched": 0}
        return []

    out = []
    for r in data.get("results", []):
        aid = str(r.get("trackId"))
        cfg = meta_by_id.get(aid, {})
        notes = (r.get("releaseNotes") or "").strip()
        version = r.get("version", "")
        rel = r.get("currentVersionReleaseDate", "")

        if not notes:
            continue

        # 只要含 AI 能力描述（含品牌名与同形字规范化）
        ai_hits = sorted(set(hit_ai(notes)))
        if not ai_hits:
            print(f"  [ - ] {cfg.get('app', r.get('trackName'))} v{version} 更新日志无 AI 内容，跳过")
            continue

        # 抽出与 AI 相关的行作为摘要，避免把「修复已知问题」混进来
        lines = [l.strip(" ·•-—\t") for l in re.split(r"[\n\r；;]", notes) if l.strip()]
        ai_lines = [l for l in lines if hit_ai(l)]
        summary = "；".join(clean_line(l) for l in ai_lines)[:120] or notes[:120]

        # 标题取 AI 信号最强的一行，而非第一行 —— 券商更新日志普遍把营销话术
        # 放在前面（「机会难捕捉，风险难规避？」），真正的能力描述在后半句。
        headline = clean_line(max(ai_lines, key=lambda l: len(hit_ai(l)))) if ai_lines else "AI 能力调整"

        blob = notes + " " + cfg.get("app", "")
        item = {
            "id": f"as-{aid}-{version}".replace(".", "_"),
            "broker": cfg.get("broker") or r.get("sellerName", ""),
            "app": cfg.get("app") or r.get("trackName", ""),
            "module": guess_module(blob),
            "type": guess_type(blob),
            "title": f"{cfg.get('app') or r.get('trackName')} v{version}：{headline[:34]}",
            "summary": summary,
            "content": notes,
            "source": "App Store 官方更新日志",
            "sourceType": "App Store",
            "sourceUrl": r.get("trackViewUrl", f"https://apps.apple.com/cn/app/id{aid}"),
            "publishedAt": to_bj(rel),
            "tags": ai_hits[:6] + [f"v{version}"],
            "analysis": {
                "版本号": version,
                "命中AI能力词": "、".join(ai_hits[:8]),
                "更新日志全文": notes[:400],
                "识别依据": "Apple iTunes Lookup 官方接口返回的 releaseNotes 字段，含 AI 能力描述",
            },
        }
        out.append(item)
        print(f"  [ + ] {item['app']} v{version}（{rel[:10]}）AI 词：{','.join(sorted(set(ai_hits))[:4])}")

    _LAST_SOURCE_STATUS["appstore"] = {
        "status": "success" if out else "empty",
        "error": "", "fetched": len(out),
    }
    return out


# ============================================================
#  源二：东方财富资讯搜索
# ============================================================

def _relevance(title, content):
    """三层过滤。返回 (是否通过, 得分, 判定说明)。"""
    # 第零层：股票行情/数据页硬否决（如"国泰海通(601211)_最新价格_行情_走势图"）
    if any(k in title for k in STOCK_PAGE_NOISE):
        return False, -100, "股票行情/数据页（非AI产品动态）"
    # 第一层：结构性否决 —— 「XX证券：」开头是研报观点的固定格式
    if RESEARCH_PREFIX.match(title):
        return False, -99, "研报观点格式（券商名冒号开头）"

    # 第二层：双维度 —— 标题必须同时含券商实体词与 AI 能力词
    tb = _hit(title, BROKER_TERMS)
    ta = _hit(title, AI_TERMS)
    if not (tb and ta):
        return False, -98, "标题未同时命中券商词与AI词"

    # 第三层：自建信号 vs 研报噪声
    neg = _hit(title, RESEARCH_NOISE)
    pos = _hit(title + " " + content[:200], BUILD_SIGNAL)
    score = len(pos) * 2 - len(neg) * 3
    if score <= 0:
        return False, score, f"研报/投资观点倾向（负向词：{'、'.join(neg[:3]) or '无正向信号'}）"
    return True, score, f"自建信号：{'、'.join(pos[:3])}"


def _eastmoney_search(keyword, page_size=20):
    param = json.dumps({
        "uid": "", "keyword": keyword, "type": ["cmsArticleWebOld"],
        "client": "web", "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {
            "searchScope": "default", "sort": "default",
            "pageIndex": 1, "pageSize": page_size}},
    }, ensure_ascii=False)
    url = "https://search-api-web.eastmoney.com/search/jsonp?cb=cb&param=" + urllib.parse.quote(param)
    raw = http_get(url)
    js = json.loads(re.sub(r"^cb\(|\);?$", "", raw.strip()))
    return (js.get("result") or {}).get("cmsArticleWebOld") or []


def _fetch_article(url):
    """抓正文；失败不影响入库，退回搜索摘要。"""
    try:
        html = http_get(url, timeout=20)
        m = re.search(r'<div[^>]+class="[^"]*(?:txtinfos|article-body|newsContent|Body)[^"]*"[^>]*>(.*?)</div>\s*<', html, re.S | re.I)
        body = strip_html(m.group(1)) if m else ""
        if len(body) < 80:
            paras = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S | re.I)
            body = "\n".join(strip_html(p) for p in paras if len(strip_html(p)) > 20)
        return body[:2000]
    except Exception:
        return ""


def parse_eastmoney_search(src, since, until):
    keywords = src.get("keywords") or ["券商 AI 智能体", "证券 大模型 应用", "券商 AI Skills"]
    page_size = int(src.get("pageSize", 20))
    fetch_body = bool(src.get("fetchBody", True))

    seen_url, cand, kept = set(), 0, []
    for kw in keywords:
        try:
            arts = _eastmoney_search(kw, page_size)
        except Exception as e:
            print(f"  [ERR ] 检索「{kw}」失败：{type(e).__name__}: {e}")
            continue

        for a in arts:
            u = a.get("url", "")
            if not u or u in seen_url:
                continue
            seen_url.add(u)
            cand += 1

            title = strip_html(a.get("title", ""))
            snippet = strip_html(a.get("content", ""))
            ok, score, why = _relevance(title, snippet)
            if not ok:
                continue

            body = _fetch_article(u) if fetch_body else ""
            blob = title + " " + (body or snippet)
            broker = guess_broker(title, body or snippet)

            pub = a.get("date", "")
            if pub and "T" not in pub:
                pub = pub.replace(" ", "T") + "+08:00"

            kept.append({
                "id": "em-" + re.sub(r"\D", "", u)[-16:],
                "broker": broker,
                "app": "—",
                "module": guess_module(blob),
                "type": guess_type(blob),
                "title": title,
                "summary": (snippet or body)[:120],
                "content": body or snippet,
                "source": a.get("mediaName") or "东方财富资讯",
                "sourceUrl": u,
                "publishedAt": pub,
                "tags": sorted(set(hit_ai(blob)))[:6],
                "analysis": {
                    "相关度得分": str(score),
                    "判定依据": why,
                    "命中AI能力词": "、".join(sorted(set(hit_ai(blob)))[:8]) or "—",
                    "涉及机构": "、".join(sorted(set(_hit(blob, BROKER_TERMS)))[:6]) or "—",
                    "检索关键词": kw,
                },
                "_score": score,
            })
            print(f"  [ + ] [{score:+d}] {title[:40]}（{a.get('mediaName')}）")

    kept.sort(key=lambda x: -x["_score"])
    for k in kept:
        k.pop("_score", None)
    print(f"  [stat] 候选 {cand} 条 → 三层过滤保留 {len(kept)} 条")
    return kept


# ============================================================
#  源三：微信 / 公众号（搜狗微信搜索）
# ============================================================

def restore_weixin_url(link_url, proxy=None):
    """把搜狗 /link?url= 跳转还原成真实 mp.weixin.qq.com 文章地址。

    搜狗反爬页用若干 `url += '...'` 片段在 <script> 里拼出真实地址，
    必须带会话 Cookie（先访问过搜索页）才能拿到这些片段；否则只返回空跳转壳。
    proxy 应与发起该搜索的出口 IP 一致（Cookie 与 IP 绑定），故由调用方透传。
    """
    try:
        r = http_get(link_url, timeout=15, referer="https://weixin.sogou.com/", proxy=proxy)
    except Exception:
        return None
    frags = re.findall(r"url\s*\+?=\s*['\"]([^'\"]+)['\"]", r)
    joined = "".join(frags)
    if "mp.weixin.qq.com" in joined:
        return joined
    m = re.search(r"https?://mp\.weixin\.qq\.com[^\s\"'\\<>]+", joined + r)
    return m.group(0) if m else None


def fetch_weixin_body(real_url, proxy=None):
    """抓微信正文（id=js_content）。失败返回空，退回搜索摘要。"""
    try:
        html = http_get(real_url, timeout=20, referer="https://weixin.sogou.com/", proxy=proxy)
        m = re.search(r'id="js_content"[^>]*>(.*?)</div>', html, re.S)
        if m:
            return strip_html(m.group(1))[:2000]
    except Exception:
        return ""
    return ""


def wechat_relevance(title, summary, account):
    """微信渠道信噪比控制。返回 (通过, 得分, 说明)。

    微信结果两类噪声：① 泛 AI 行业爆款（无券商主体）；② 券商研究观点。
    核心过滤：必须同时含 AI 能力词 + 券商/证券实体上下文（标题/摘要/公众号名）。
    """
    full = f"{title} {summary} {account}"
    if RESEARCH_PREFIX.match(title):
        return False, -99, "研报观点格式（券商名冒号开头）"
    ai = _hit(full, AI_TERMS) + _hit(full, AI_BRANDS)
    if not ai:
        return False, -97, "无 AI 能力词"
    ctx = _hit(full, BROKER_TERMS)
    if "券商" in full or "证券" in full:
        ctx = ctx + ["券商"]
    if not ctx:
        return False, -96, "无券商/证券上下文（非券业 AI 动态）"
    neg = _hit(full, RESEARCH_NOISE)
    pos = _hit(full, BUILD_SIGNAL)
    score = len(pos) * 2 - len(neg) * 3
    if score <= -6:
        return False, score, f"偏研报/投资观点（负向词：{','.join(neg[:3])}）"
    return True, score, f"券商 AI 动态（{'、'.join(ai[:3])}）"


def parse_sogou_wechat(src, since, until):
    """微信 / 公众号搜索（搜狗微信）。

    同时服务两类需求：
      - 全网+微信行业资讯（keywords）：检索「券商 AI 智能体」等泛关键词；
      - 官方源（official=true, queries 带 broker）：逐家券商官方公众号定向检索，
        命中即视为该券商官方动态，是「官网源」的可行替代（券商官网多为 SPA/404）。

    是否「新」由 collect.py 指纹库判定（与时间窗口无关）——微信文章发布频率低，
    靠时间过滤会漏采；指纹库让首次出现的文章即被捕获，旧文（如去年）首次出现时
    自动打 backfill 标记，界面按需求 #3 显示年份。
    """
    queries = src.get("queries") or [{"kw": k} for k in (src.get("keywords") or [])]
    official = bool(src.get("official"))
    max_per = int(src.get("maxPerQuery", 8))
    fetch_body = bool(src.get("fetchBody", False))
    max_body = int(src.get("maxBody", 2))
    query_delay = float(src.get("queryDelay", 0.8))
    body_count, out, seen_link = 0, [], set()
    # 限流时按代理池轮换出口 IP。无代理则直接重试（短退避）。
    max_attempts = max(2, 1 + min(len(_PROXIES), 6))

    for q in queries:
        kw = (q.get("kw") or q.get("query") or "").strip()
        prefer = q.get("broker")
        if not kw:
            continue

        html = None
        cur_proxy = None
        for attempt in range(max_attempts):
            cur_proxy = _ROTATOR.next()
            try:
                url = ("https://weixin.sogou.com/weixin?type=2&query="
                       + urllib.parse.quote(kw) + "&ie=utf8&_sug_=n&_sug_type_=")
                html = http_get(url, timeout=25, referer="https://weixin.sogou.com/", proxy=cur_proxy)
            except Exception as e:
                print(f"  [ERR ] 微信检索「{kw}」失败：{type(e).__name__}: {e}")
                time.sleep(1)
                break
            if not is_antibot(html):
                break
            # 触发反爬验证页 → 换下一个代理（或直连接口短退避）
            tag = cur_proxy or "直连接口"
            print(f"  [WARN] 搜狗限流（{tag}），切换出口 IP 重试（{attempt+1}/{max_attempts}）")
            time.sleep(3)
        if not html or is_antibot(html):
            print("  [WARN] 搜狗持续限流，放弃本轮微信采集")
            break

        parts = re.split(r'<li[^>]*id="sogou_vr_11002601_box_\d+"', html)
        cnt = 0
        for box in parts[1:]:
            box = "<li" + box
            h3 = re.search(r"<h3>(.*?)</h3>", box, re.S)
            if not h3:
                continue
            a = re.search(r'href="(/link\?url=[^"&]+)"', h3.group(1))
            if not a:
                continue
            title = strip_html(h3.group(1)).strip()
            link = "https://weixin.sogou.com" + a.group(1)
            if link in seen_link:
                continue
            seen_link.add(link)

            ac = re.search(r'class="all-time-y2[^"]*"[^>]*>(.*?)</span>', box, re.S)
            account = strip_html(ac.group(1)).strip() if ac else ""
            sn = re.search(r'class="txt-info"[^>]*>(.*?)</div>', box, re.S)
            summary = strip_html(sn.group(1)).strip() if sn else ""
            tc = re.search(r"timeConvert\('(\d+)'\)", box)
            pub = ""
            if tc:
                try:
                    pub = datetime.fromtimestamp(int(tc.group(1))).strftime("%Y-%m-%dT%H:%M:%S+08:00")
                except Exception:
                    pub = ""

            ok, score, why = wechat_relevance(title, summary, account)
            if not ok:
                continue

            real = restore_weixin_url(link, cur_proxy)
            source_url = real or link

            if prefer and (prefer in title or prefer in account or prefer in summary):
                broker = prefer
            else:
                broker = guess_broker(title, summary + " " + account)

            content = summary
            if fetch_body and body_count < max_body and real and len(summary) < 80:
                b = fetch_weixin_body(real, cur_proxy)
                if b:
                    content = b
                    body_count += 1

            blob = title + " " + content
            if official and account:
                src_label = account + " · 官方公众号"
            elif account:
                src_label = account + " · 微信公众号"
            else:
                src_label = "微信公众号"

            out.append({
                "id": "wx-" + hashlib.md5((kw + link).encode("utf-8")).hexdigest()[:14],
                "broker": broker,
                "app": "—",
                "module": guess_module(blob),
                "type": guess_type(blob),
                "title": title,
                "summary": summary[:160],
                "content": content,
                "source": src_label,
                "sourceType": "微信公众号",
                "sourceUrl": source_url,
                "publishedAt": pub,
                "tags": sorted(set(hit_ai(blob)))[:6],
                "analysis": {
                    "相关度得分": str(score),
                    "判定依据": why,
                    "命中AI能力词": "、".join(sorted(set(hit_ai(blob)))[:8]) or "—",
                    "来源公众号": account or "—",
                    "检索关键词": kw,
                    "来源类型": "官方公众号" if official else "微信资讯",
                },
                "_score": score,
            })
            cnt += 1
            if cnt >= max_per:
                break

        print(f"  [ + ] 微信检索「{kw}」→ 命中 {cnt} 条")
        if query_delay:
            time.sleep(query_delay)

    out.sort(key=lambda x: -x["_score"])
    for k in out:
        k.pop("_score", None)
    print(f"  [stat] 微信源共 {len(out)} 条")
    return out


# ============================================================
#  源四：全网新闻搜索（Bing News）
# ============================================================

def _bing_news_search(query, count=20, proxy=None):
    """Bing 新闻搜索，返回结构化结果列表。proxy 用于轮换出口 IP。"""
    url = ("https://www.bing.com/news/search?q="
           + urllib.parse.quote(query)
           + "&setlang=zh-CN&cc=CN&count=" + str(count))
    html = http_get(url, timeout=20, referer="https://www.bing.com/", proxy=proxy)
    results = []
    # Bing News 结果项
    for m in re.finditer(r'<a[^>]+class="title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        href = m.group(1)
        title = strip_html(m.group(2)).strip()
        if not title:
            continue
        # 找该条目所在的父容器以提取摘要和来源
        # 向前找最近的 news-card / result 容器
        start = max(0, html.index(m.group(0)) - 2000)
        chunk = html[start:html.index(m.group(0)) + len(m.group(0)) + 2000]
        sn = re.search(r'<p[^>]*class="snippet"[^>]*>(.*?)</p>', chunk, re.S)
        summary = strip_html(sn.group(1)).strip() if sn else ""
        src_m = re.search(r'<span[^>]*class="source"[^>]*>(.*?)</span>', chunk, re.S)
        source = strip_html(src_m.group(1)).strip() if src_m else "Bing新闻"
        # 时间
        time_m = re.search(r'<span[^>]*(?:time|date)[^>]*>(.*?)</span>', chunk, re.S | re.I)
        pub_str = strip_html(time_m.group(1)).strip() if time_m else ""
        results.append({
            "title": title,
            "url": href,
            "summary": summary[:200],
            "source": source,
            "pub_str": pub_str,
        })
    return results


def _parse_bing_relative_time(s):
    """解析 Bing 的相对时间（如 '3小时前'、'昨天'、'2天前'）为 ISO。"""
    s = s.strip()
    now = datetime.now(timezone(timedelta(hours=8)))
    m = re.match(r"(\d+)\s*小时前", s)
    if m:
        dt = now - timedelta(hours=int(m.group(1)))
        return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    m = re.match(r"(\d+)\s*天前", s)
    if m:
        dt = now - timedelta(days=int(m.group(1)))
        return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    if "昨天" in s:
        dt = now - timedelta(days=1)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    if "前天" in s:
        dt = now - timedelta(days=2)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    # 尝试绝对日期
    for fmt in ["%Y年%m月%d日", "%Y-%m-%d", "%m月%d日"]:
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%m月%d日":
                dt = dt.replace(year=now.year)
            return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except Exception:
            continue
    return ""


def parse_bing_news(src, since, until):
    """Bing 全网新闻搜索。

    覆盖面广（搜索引擎聚合了各新闻源），适合捕捉：
      - 券商 AI 产品发布/升级的新闻报道
      - 行业媒体对券商 AI 动态的跟进
      - 监管/备案类合规动态（自动归入「法律合规」分类）
    """
    keywords = src.get("keywords") or [
        "券商 AI 智能体", "证券公司 大模型", "券商 人工智能 应用",
        "证券业 算法备案", "券商 AI 投顾", "华泰证券 AI",
        "国泰海通 灵犀", "广发证券 AI", "中信证券 大模型",
    ]
    max_per = int(src.get("maxPerQuery", 6))
    fetch_body = bool(src.get("fetchBody", True))
    query_delay = float(src.get("queryDelay", 1.5))

    seen_url, out = set(), []
    for kw in keywords:
        try:
            results = _bing_news_search(kw, count=max_per * 2, proxy=_ROTATOR.next())
        except Exception as e:
            print(f"  [ERR ] Bing检索「{kw}」失败：{type(e).__name__}: {e}")
            time.sleep(1)
            continue

        cnt = 0
        for r in results:
            u = r["url"]
            if not u or u in seen_url:
                continue
            seen_url.add(u)

            title = r["title"]
            summary = r["summary"]
            source = r["source"]

            # 信噪比过滤（复用三层逻辑）
            ok, score, why = _relevance(title, summary)
            # 对合规类关键词放宽过滤（备案/监管新闻可能不含 BUILD_SIGNAL）
            compliance_kws = ["备案", "算法备案", "模型备案", "网信办", "深度合成", "生成式AI服务管理办法", "法规", "办法", "规定", "指引", "征求意见"]
            if not ok and not any(k in title for k in STOCK_PAGE_NOISE) and any(k in (title + " " + summary) for k in compliance_kws):
                ai_hit = _hit(title + " " + summary, AI_TERMS + AI_BRANDS)
                broker_hit = _hit(title + " " + summary, BROKER_TERMS)
                if ai_hit and broker_hit:
                    ok = True
                    score = 3
                    why = f"合规/监管动态（{','.join(compliance_kws)}）"

            if not ok:
                continue

            body = ""
            if fetch_body and len(summary) < 40:
                try:
                    body = _fetch_article(u)
                except Exception:
                    pass

            blob = title + " " + (body or summary)
            broker = guess_broker(title, body or summary)

            pub = _parse_bing_relative_time(r.get("pub_str", ""))

            out.append({
                "id": "bn-" + hashlib.md5((kw + u).encode("utf-8")).hexdigest()[:14],
                "broker": broker,
                "app": "—",
                "module": guess_module(blob),
                "type": guess_type(blob),
                "title": title,
                "summary": (body or summary)[:160],
                "content": body or summary,
                "source": source + " · Bing新闻",
                "sourceType": "全网新闻",
                "sourceUrl": u,
                "publishedAt": pub,
                "tags": sorted(set(hit_ai(blob)))[:6],
                "analysis": {
                    "相关度得分": str(score),
                    "判定依据": why,
                    "命中AI能力词": "、".join(sorted(set(hit_ai(blob)))[:8]) or "—",
                    "涉及机构": "、".join(sorted(set(_hit(blob, BROKER_TERMS)))[:6]) or "—",
                    "检索关键词": kw,
                    "新闻来源": source,
                },
                "_score": score,
            })
            cnt += 1
            if cnt >= max_per:
                break

        print(f"  [ + ] Bing检索「{kw}」→ 命中 {cnt} 条")
        if query_delay:
            time.sleep(query_delay)

    out.sort(key=lambda x: -x["_score"])
    for k in out:
        k.pop("_score", None)
    print(f"  [stat] Bing新闻源共 {len(out)} 条")
    return out


# ============================================================
#  源五：Tavily 全网搜索（真·全网，免代理，云上用）
# ============================================================

def _tavily_search(query, api_key, max_results=8):
    """Tavily Search API（POST https://api.tavily.com/search）。
    返回 [{title, url, content}]；失败返回 []。"""
    body = json.dumps({
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": int(max_results),
        "include_answer": False,
        "include_raw_content": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search", data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30, context=_CTX) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    return data.get("results") or []


def parse_tavily(src, since, until):
    """Tavily 全网搜索（云版广度源）。

    覆盖面远大于单一财经站：Tavily 聚合全网网页，适合捕捉东方财富索引不到的
    券商 AI 动态（官网公告、科技媒体、地方媒体、备案公示等）。
    需环境变量 TAVILY_API_KEY；未配置时静默跳过（不影响其他源）。
    信噪比复用三层过滤 + 合规类放宽（与 bing_news 同口径）。
    是否「新」由 collect.py 指纹库判定。
    """
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        print("  [skip] Tavily 未配置 TAVILY_API_KEY，跳过")
        _LAST_SOURCE_STATUS["tavily"] = {
            "status": "skipped", "error": "no key", "fetched": 0,
            "note": "未配置 TAVILY_API_KEY（可选源，跳过）"}
        return []

    queries = src.get("queries") or [{"kw": k} for k in (src.get("keywords") or [])]
    max_per = int(src.get("maxPerQuery", 8))
    query_delay = float(src.get("queryDelay", 1.0))
    compliance_kws = ["备案", "算法备案", "模型备案", "网信办", "深度合成", "生成式AI服务管理办法", "法规", "办法", "规定", "指引", "征求意见"]

    seen_url, out = set(), []
    for q in queries:
        kw = (q.get("kw") if isinstance(q, dict) else q) or ""
        kw = kw.strip()
        if not kw:
            continue
        try:
            results = _tavily_search(kw, api_key, max_per)
        except Exception as e:
            print(f"  [ERR ] Tavily 检索「{kw}」失败：{type(e).__name__}: {e}")
            _LAST_SOURCE_STATUS["tavily"] = {"status": "failed",
                "error": f"{type(e).__name__}: {e}", "fetched": len(out)}
            return out

        cnt = 0
        for r in results:
            u = r.get("url", "")
            if not u or u in seen_url:
                continue
            seen_url.add(u)
            title = strip_html(r.get("title", ""))
            summary = strip_html(r.get("content", ""))
            if not title:
                continue

            ok, score, why = _relevance(title, summary)
            if not ok and not any(k in title for k in STOCK_PAGE_NOISE) and any(k in (title + " " + summary) for k in compliance_kws):
                ai_hit = _hit(title + " " + summary, AI_TERMS + AI_BRANDS)
                broker_hit = _hit(title + " " + summary, BROKER_TERMS)
                if ai_hit and broker_hit:
                    ok, score, why = True, 3, f"合规/监管动态（{','.join(compliance_kws[:3])}）"
            if not ok:
                continue

            blob = title + " " + summary
            broker = guess_broker(title, summary)
            out.append({
                "id": "tv-" + hashlib.md5((kw + u).encode("utf-8")).hexdigest()[:14],
                "broker": broker,
                "app": "—",
                "module": guess_module(blob),
                "type": guess_type(blob),
                "title": title,
                "summary": summary[:160],
                "content": summary,
                "source": "Tavily · 全网搜索",
                "sourceType": "全网新闻",
                "sourceUrl": u,
                "publishedAt": "",
                "tags": sorted(set(hit_ai(blob)))[:6],
                "analysis": {
                    "相关度得分": str(score),
                    "判定依据": why,
                    "命中AI能力词": "、".join(sorted(set(hit_ai(blob)))[:8]) or "—",
                    "涉及机构": "、".join(sorted(set(_hit(blob, BROKER_TERMS)))[:6]) or "—",
                    "检索关键词": kw,
                },
                "_score": score,
            })
            cnt += 1

        print(f"  [ + ] Tavily 检索「{kw}」→ 命中 {cnt} 条")
        if query_delay:
            time.sleep(query_delay)

    out.sort(key=lambda x: -x["_score"])
    for k in out:
        k.pop("_score", None)
    _LAST_SOURCE_STATUS["tavily"] = {
        "status": "success" if out else "empty", "error": "", "fetched": len(out)}
    print(f"  [stat] Tavily 全网搜索源共 {len(out)} 条")
    return out


# ============================================================
#  源六：AI 联网搜索（自动化 WebSearch 写出）
# ============================================================

def parse_websearch_raw(src, since, until):
    """读取每日自动化通过 WebSearch 写出的联网搜索结果（scripts/websearch_raw.json）。

    字段由自动化 agent 抽取并产出，本函数只做标准化：
      - 补全 broker（未提供则推断）、module/type（统一走现有分类器，保证与其他源口径一致）
      - 组装 tags 与 analysis
    是否「新」由 collect.py 指纹库判定（与时间窗口无关）。
    读取后即清空文件（避免重复摄入；去重另有指纹库兜底）。
    """
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
    path = src.get("file") or "scripts/websearch_raw.json"
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    search_status = (data.get("meta") or {}).get("searchStatus") if isinstance(data, dict) else None

    # 读取后清空（留空壳），下次运行由自动化重新写出
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"items": []}, f, ensure_ascii=False)
    except Exception:
        pass

    out = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        summary = (it.get("summary") or "").strip()
        blob = title + " " + summary
        broker = it.get("broker") or guess_broker(title, summary)
        url = (it.get("sourceUrl") or "").strip()
        raw_source = (it.get("source") or "联网搜索") + " · AI联网搜索"
        out.append({
            "id": "ws-" + hashlib.md5((url or title).encode("utf-8")).hexdigest()[:14],
            "broker": broker,
            "app": "—",
            "module": guess_module(blob),
            "type": guess_type(blob),
            "title": title,
            "summary": summary[:160],
            "content": summary,
            "source": raw_source,
            "sourceType": it.get("sourceType") or _derive_channel(raw_source),
            "sourceUrl": url,
            "publishedAt": (it.get("publishedAt") or "")[:25],
            "tags": sorted(set(hit_ai(blob)))[:6],
            "analysis": {
                "来源类型": "AI联网搜索（自动化 WebSearch）",
                "命中AI能力词": "、".join(sorted(set(hit_ai(blob)))[:8]) or "—",
                "涉及机构": "、".join(sorted(set(_hit(blob, BROKER_TERMS)))[:6]) or "—",
                "检索/抽取": "自动化 WebSearch + 大模型抽取",
            },
        })

    # 回填采集窗口所需的「联网搜索」源状态（由自动化 agent 在 WebSearch 后写入 meta.searchStatus）
    if search_status:
        _LAST_SOURCE_STATUS["websearch_raw"] = {
            "status": search_status.get("status", "success"),
            "error": search_status.get("error", ""),
            "fetched": len(out),
            "queryCount": search_status.get("queryCount"),
            "candidates": search_status.get("candidates"),
            "note": search_status.get("note", ""),
        }
    else:
        _LAST_SOURCE_STATUS["websearch_raw"] = {
            "status": "success" if out else "empty", "error": "", "fetched": len(out),
        }
    print(f"  [stat] 联网搜索源共 {len(out)} 条")
    return out


# ============================================================
#  分发
# ============================================================

PARSERS = {
    "appstore": parse_appstore,
    "eastmoney_search": parse_eastmoney_search,   # 已停用：sources.json 中 disabled
    "sogou_wechat": parse_sogou_wechat,
    "bing_news": parse_bing_news,
    "tavily": parse_tavily,                       # 云版真·全网搜索（需 TAVILY_API_KEY，未配置自动跳过）
    "websearch_raw": parse_websearch_raw,         # 自动化 WebSearch 写出 → collect.py 并入
}


def dispatch(src, since, until):
    fn = PARSERS.get(src.get("type"))
    if not fn:
        print(f"  [skip] 「{src.get('name','?')}」解析器未实现（type={src.get('type')}）")
        return []
    if not src.get("enabled", True):
        print(f"  [skip] 「{src.get('name','?')}」已禁用")
        return []
    print(f"  [run ] {src.get('name','?')}（{src.get('type')}）")
    try:
        return fn(src, since, until)
    except Exception as e:
        print(f"  [ERR ] 「{src.get('name','?')}」解析异常：{type(e).__name__}: {e}")
        return []
