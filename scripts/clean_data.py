# -*- coding: utf-8 -*-
"""一次性数据清洗：移除股票行情页 + 跨源转载重复（子串包含去重）。
操作 collect.DATA_DIR/data.json（就地清洗并 rebuild meta）。"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect, parsers

path = os.path.join(collect.DATA_DIR, "data.json")
d = json.load(open(path, encoding="utf-8"))
items = d.get("items", [])
meta = d.get("meta", {})

# 1) 移除股票行情/数据页
no_stock = [it for it in items if not any(k in it.get("title", "") for k in parsers.STOCK_PAGE_NOISE)]
removed_stock = len(items) - len(no_stock)

# 2) 跨源转载子串去重（保留首条）
accepted = []
final = []
for it in no_stock:
    nt = collect._norm_title_dedup(it.get("title", ""))
    if nt and len(nt) >= 12 and any((nt in at) or (at in nt) for at in accepted):
        continue
    if nt:
        accepted.append(nt)
    final.append(it)
removed_dup = len(no_stock) - len(final)

print(f"[clean] {len(items)} -> {len(final)}  (移除股票页 {removed_stock}，跨源重复 {removed_dup})")
# rebuild meta 并写回
collect.rebuild_data(final, meta, None)
print("[clean] 已写回", path)
