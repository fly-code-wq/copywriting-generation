# 联网检索用法 (web-search.md)

`scripts/web_search.py` 用于**本地文案库不够用时**，临时联网检索类似文案作为补充素材。

## 用法

```bash
# 自动选择 provider（推荐）
python scripts/web_search.py --query "小红书 文案 治愈 旅行" --top 5

# 强制 Tavily
python scripts/web_search.py --query "..." --provider tavily --top 5

# 强制 WebFetch（无 API key）
python scripts/web_search.py --query "..." --provider webfetch --top 3

# JSON 输出
python scripts/web_search.py --query "..." --json
```

## Provider 列表

### tavily（推荐）

- 优点：结果质量高，专为 LLM 设计
- 需要：`TAVILY_API_KEY` 环境变量
- 安装：`pip install tavily-python`

```bash
export TAVILY_API_KEY="tvly-xxxxxxxx"
python scripts/web_search.py --query "西湖 旅行 治愈" --provider tavily --top 5
```

### webfetch（兜底）

- 优点：零依赖，纯标准库
- 缺点：基于 DuckDuckGo HTML 抓取，结果质量与稳定性有限
- 适用：临时用、没有 API key 时

```bash
python scripts/web_search.py --query "西湖 旅行 治愈" --provider webfetch --top 5
```

## 自动 fallback 流程

```
--provider auto
   │
   ├─ 尝试 tavily (需要 API key + 库安装)
   │     ├─ 成功 → 返回结果
   │     └─ 失败 → fallback 到 webfetch
   │
   └─ 直接 webfetch
```

## 在 copygen 主流程中使用

```bash
python scripts/copygen.py \
  --scene "今天去了西湖" \
  --platform xiaohongshu \
  --n 5 \
  --web --web-provider auto
```

返回结构中多了 `web_hits` 字段，智能体可把它当作额外参考素材。

## 检索结果格式

```json
[
  {
    "url": "https://...",
    "title": "30 条治愈系西湖文案",
    "snippet": "雨后的西湖真的太治愈了..."
  },
  ...
]
```

`url` 在 webfetch 模式下可能为空。

## 检索 Query 模板

为了拿到更精准的结果，建议智能体**先拼好 query 再调用**：

```python
query = f"{intent['platform']} {intent['scene']} {intent['tone']} {scene_text}".strip()
```

示例：
```
"xiaohongshu travel warm 今天去了西湖"
```

## 联网结果去重

联网拿到的结果**一定要过 `scripts/dedupe.py`**，避免拼凑出侵权文案：

```bash
# 先把 web_hits 转成 candidates.jsonl
python -c "
import json, sys
hits = json.loads(sys.stdin.read())
with open('web_candidates.jsonl', 'w', encoding='utf-8') as f:
    for h in hits:
        f.write(json.dumps({'text': h.get('snippet',''), 'source': h.get('url','')}, ensure_ascii=False) + '\n')
" < web_hits.json

# 再过 dedupe
python scripts/dedupe.py --candidates web_candidates.jsonl --against assets/seed_corpus.jsonl
```

## 限流与成本

- Tavily 按调用次数计费，免费额度约 1000 次/月
- 每次 --top N 表示一次 API 调用，N 大小不影响费用
- 建议**本地库不足时**才走联网，不要每次都联网

## 合规

- 联网结果**仅作为灵感素材**，不要直接拷贝粘贴
- 智能体融合改写后，与原文相似度 ≤ 0.7（jaccard）才可输出
- 涉及版权平台（小红书、知乎）的内容仅作为参考，不直接复用

## 安全

- 不要把 web 检索结果写入本地文案库（避免污染）
- 联网结果里如含敏感词（色情、暴力、政治），智能体必须过滤