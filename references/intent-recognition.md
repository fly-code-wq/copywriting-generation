# 意图识别方法论 (intent-recognition.md)

智能体收到"用户随口的一句话"后，必须先识别出 4 个关键维度，再去检索 + 生成：

| 维度 | 含义 | 例子 |
|------|------|------|
| **platform** | 目标平台 | xiaohongshu / douyin / wechat_moments / weibo / zhihu / bilibili / twitter / instagram |
| **scene** | 内容场景 | travel / food / fashion / lifestyle / tech / beauty / fitness / parenting / work / study / emotion |
| **tone** | 情绪基调 | warm / humor / luxury / energetic / calm / ironic / professional |
| **style** | 内容类型 | 种草 / 测评 / 教程 / 打卡 / 吐槽 / 科普 / 情感 / 带货 / 段子 |

这 4 个维度决定后续的：① 用哪个平台的风格卡 ② 从文案库的哪个子集检索 ③ 生成时套哪个 hook 公式 ④ 用哪个语气调教。

---

## 1. 平台识别

**关键词词典**（保存在 `assets/platform_keywords.json`，可由用户扩展）：

```json
{
  "xiaohongshu":     ["小红书", "xhs", "red", "种草", "姐妹"],
  "douyin":          ["抖音", "dy", "tiktok", "短视频", "口播"],
  "wechat_moments":  ["朋友圈", "好友圈", "发圈"],
  "weibo":           ["微博", "weibo", "热搜"],
  "zhihu":           ["知乎", "zhihu"],
  "bilibili":        ["b站", "b 站", "bilibili", "哔哩哔哩", "小破站"],
  "twitter":         ["twitter", "推特", "x 平台", "x平台"],
  "instagram":       ["instagram", "ins", "IG"]
}
```

**判定优先级**：
1. 用户**显式传 --platform 参数（如 `--platform douyin`）** → 100% 信任
2. 场景描述里直接出现平台名 → 高置信
3. 出现平台特色词（如"姐妹"→小红书，"钩子"→抖音）→ 中置信
4. 完全没说 → 默认 `xiaohongshu`（最通用）或要求用户澄清

---

## 2. 场景识别

**关键词词典**：

```json
{
  "travel":    ["旅行", "出游", "旅游", "出行", "打卡", "景点", "度假", "自驾"],
  "food":      ["美食", "吃", "探店", "餐厅", "夜宵", "下午茶", "咖啡", "甜品", "奶茶"],
  "fashion":   ["穿搭", "搭配", "ootd", "秋冬", "春夏", "单品", "上新", "限量"],
  "lifestyle": ["生活", "日常", "家居", "vlog", "周末", "仪式感"],
  "tech":      ["数码", "测评", "开箱", "新机", "手机", "电脑", "耳机"],
  "beauty":    ["护肤", "彩妆", "口红", "粉底", "面膜", "医美"],
  "fitness":   ["健身", "跑步", "瑜伽", "撸铁", "减肥", "塑形"],
  "parenting": ["宝宝", "娃", "育儿", "母婴", "亲子", "幼儿园"],
  "work":      ["上班", "打工", "加班", "述职", "汇报", "客户"],
  "study":     ["考研", "考证", "学习", "备考", "期末"],
  "emotion":   ["emo", "治愈", "伤感", "心情", "感悟", "回忆"]
}
```

**判定方法**：
- 文本分词 → 在场景词典里找命中 → 命中数最多的场景胜出
- 平局时按"特定词优先"：`景点`、`探店`、`穿搭`、`健身` 等单字词比"日常"这种模糊词更优先
- 都没命中 → `other`

---

## 3. 情绪基调识别

**关键词词典**：

```json
{
  "warm":         ["温暖", "治愈", "暖心", "温柔"],
  "humor":        ["搞笑", "段子", "好玩", "逗"],
  "luxury":       ["高级", "精致", "轻奢", "高级感"],
  "energetic":    ["燃", "炸", "爆", "热血", "热血沸腾"],
  "calm":         ["安静", "宁静", "岁月静好", "平淡"],
  "ironic":       ["吐槽", "反讽", "阴阳怪气"],
  "professional": ["专业", "理性", "严肃", "深度"]
}
```

**判定方法**：找命中数最多的 tone；如果用户没明确说，**默认 `warm`**（最不容易翻车）。

---

## 4. 内容类型识别

**关键词词典**：

```json
{
  "种草": ["种草", "安利", "推荐", "好物"],
  "测评": ["测评", "评测", "体验"],
  "教程": ["教程", "攻略", "指南", "怎么"],
  "打卡": ["打卡", "vlog", "记录"],
  "吐槽": ["吐槽", "避雷", "拔草"],
  "科普": ["科普", "涨知识", "原理"],
  "情感": ["情感", "感悟", "故事"],
  "带货": ["带货", "直播间", "优惠"],
  "段子": ["段子", "梗", "玩梗"]
}
```

**判定方法**：同 tone，找命中数最多；如果没说，**默认 `种草`（小红书/微博）或 `打卡`（朋友圈/抖音）**，视 platform 而定。

---

## 5. 综合示例

| 用户输入 | 识别结果 |
|---------|---------|
| "我今天去了西湖，帮我写条小红书" | platform=xiaohongshu, scene=travel, tone=warm, style=打卡 |
| "给这条抖音视频配个标题" | platform=douyin, scene=other, tone=energetic, style=段子 |
| "我想发个朋友圈，高级感一点" | platform=wechat_moments, scene=lifestyle, tone=luxury, style=情感 |
| "这是个新品，给我写几个 slogan" | platform=other(自动选 xiaohongshu), scene=fashion, tone=lively, style=种草 |
| "这段文案太土了，帮我润色下" | platform=见原文, tone=见原文, scene=见原文, style=见原文 |

---

## 6. 调用方法

### Python 模块调用

```python
from scripts.lib.intent import recognize

result = recognize("今天去了西湖，帮我写条小红书",
                   assets_dir=Path("assets"),
                   explicit_platform="xiaohongshu")
print(result)
# {
#   "platform": "xiaohongshu",
#   "scene": "travel",
#   "tone": "warm",
#   "style": "打卡",
#   "confidence": 0.83,
#   "raw_keywords": {...}
# }
```

### CLI 调用

```bash
python -c "from scripts.lib.intent import recognize; import json; \
  print(json.dumps(recognize('今天去了西湖，帮我写条小红书'), ensure_ascii=False, indent=2))"
```

### 智能体直接读取本文件

如果智能体本身已经够强，可以跳过 Python 调用，直接按上面 4 个词典人工判断，把结果写进 prompt。

---

## 7. 扩展词典

把新的关键词加入 `assets/platform_keywords.json`：

```json
{
  "scene": {
    "travel": {"aliases": ["旅行", "出游", "旅游", "自驾", "小众", "city walk"]}
  },
  "tone": {
    "literary": {"aliases": ["文艺", "诗意"], "weight": 1.0}
  }
}
```

权重说明：
- `weight` 默认 1.0，>1 表示更倾向，<1 表示弱倾向
- 同时出现多平台/多 scene 关键词时，分数 = 命中数 × weight

---

## 8. 意图置信度

`confidence` 字段含义：
- `0.0 - 0.3`：建议智能体追问用户（"你希望发在哪个平台？"）
- `0.3 - 0.7`：按识别结果生成，但留 fallback（"如果想换平台，告诉我"）
- `0.7 - 1.0`：直接按识别结果生成，无需追问