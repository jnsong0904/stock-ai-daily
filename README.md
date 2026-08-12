# 证券业 AI 动态日报 · 竞品调研站

每日自动采集券商/证券业自建 AI 动态，生成静态站点。**云端自治**：GitHub Actions 每个交易日 08:30（北京时间）自动采集 → 更新数据 → GitHub Pages 自动发布，无需任何本地电脑开机。

## 架构

```
GitHub Actions (cron 00:30 UTC = 08:30 北京, 周一-五)
   │
   ├─ scripts/collect.py        采集管线（交易日判断 + 指纹去重 + 分类 + 窗口并入）
   │     ├─ appstore            Apple iTunes Lookup API（免 key，券商 APP AI 版本更新日志）
   │     └─ eastmoney_search    东方财富资讯搜索 API（免 key，全网新闻，三层过滤）
   │
   ├─ 回写 site/data/data.json + scripts/seen.json（指纹库，跨日去重）
   ├─ scripts/notify_feishu.py  飞书群 webhook 推送（可选，配 Secrets）
   └─ 部署 site/ → GitHub Pages
```

- 数据源配置：`scripts/sources.cloud.json`（云端，免 key）。本地 WorkBuddy 流程用 `scripts/sources.json`（含 websearch_raw）。
- 站点三页（今日 / 历史归档 / 竞品矩阵）由同一份 `site/data/data.json` 驱动。
- 时间窗口：上一交易日 08:30 → 今日 08:30（周一覆盖周末，节后首日自动回溯）。非交易日跳过。
- 双闸门：① 指纹去重（URL+标题哈希）② 新鲜度分级（≤30天正常，>30天补录）。

## 本地运行

```bash
# 云端配置（免 key）
SEC_AI_SOURCES=scripts/sources.cloud.json python scripts/collect.py
# 本地 WorkBuddy 配置（含 WebSearch）
python scripts/collect.py
```

纯 Python 标准库，无需 pip install。

## 一次性启用步骤

1. 推送到 GitHub（公开仓库，Pages 免费需公开）。
2. 仓库 Settings → Pages → Source 选 **GitHub Actions**。
3. （可选）Settings → Secrets 添加 `FEISHU_WEBHOOK`（飞书群机器人 webhook）。
4. Actions 页面手动触发一次「证券业AI日报-每日采集」验证。
