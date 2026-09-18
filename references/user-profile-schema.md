# 用户画像 Schema 与更新算法 (user-profile-schema.md)

画像文件路径：`data/user_profile.json`（可由 `--profile` 自定义）。

## Schema 完整定义

```json
{
  "user_id": "default",
  "version": 1,
  "created_at": "2026-09-18T08:00:00Z",
  "updated_at": "2026-09-18T08:00:00Z",

  "demographics": {
    "age_range": "20-25",          // "10-15" / "15-20" / "20-25" / "25-30" / "30-40" / "40+"
    "gender_guess": "female",      // "male" / "female" / "non-binary" / "unknown"
    "region_guess": "CN-East"      // 自由字符串 / ""
  },

  "language_style": {
    "emoji_density": 0.5,          // [0, 1]，0=不用，1=满屏
    "punctuation_pref": ["！！", "～"],   // 标点偏好（按频次）
    "sentence_length": "short",     // "short" (<30) / "medium" (30-80) / "long" (>80)
    "sentence_length_pref": {"short": 0.6, "medium": 0.3, "long": 0.1},
    "fav_words": ["绝绝子", "氛围感", "宝子们"]              // 常用词，按频次
  },

  "platform_affinity": {            // 平台偏好 0~1
    "xiaohongshu": 0.9,
    "douyin": 0.3,
    "wechat_moments": 0.6,
    "weibo": 0.5,
    "zhihu": 0.5,
    "bilibili": 0.4,
    "twitter": 0.2,
    "instagram": 0.3
  },

  "topic_interests": {              // 场景兴趣 0~1
    "travel": 0.85, "food": 0.6, "fashion": 0.7, "lifestyle": 0.5,
    "tech": 0.3, "beauty": 0.6, "fitness": 0.3, "parenting": 0.1,
    "work": 0.4, "study": 0.2, "emotion": 0.5, "other": 0.3
  },

  "tone_preference": {              // 情绪偏好 0~1
    "warm": 0.7, "humor": 0.4, "luxury": 0.2,
    "energetic": 0.5, "calm": 0.4, "ironic": 0.2, "professional": 0.3
  },

  "feedback_history": [             // 原始反馈日志（最多保留 200 条）
    {
      "ts": "2026-09-18T08:00:00Z",
      "scene": "今天去了西湖",
      "platform": "xiaohongshu",
      "tone": "warm",
      "style": "打卡",
      "chosen_index": 2,
      "reason_keywords": ["emoji密集", "姐妹风"],
      "chosen_text_preview": "家人们，雨后西湖真的氛围感拉满 🍃…"
    }
  ]
}
```

## 字段约束

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | string | "default" | 多用户时唯一标识 |
| `version` | int | 1 | 每次更新 +1，便于追踪 |
| `platform_affinity` keys | set | 8 个平台 | 不可改键名 |
| `topic_interests` keys | set | 12 个场景 | 不可改键名 |
| `tone_preference` keys | set | 7 种 tone | 不可改键名 |
| 数值字段 | float in [0, 1] | 0.5 | 钳制范围 |
| `feedback_history` | array | [] | 最多保留 200 条 |

---

## 更新算法

智能体收到反馈后，调用 `scripts/profile.py update --feedback JSON`，内部按以下规则更新：

### 1. EMA 更新（α=0.15）

对 `platform_affinity[chosen_platform]`：
```
new = old * (1 - 0.15) + 1.0 * 0.15
```
其余平台做**轻微负向**更新（让画像分布更聚焦）：
```
new = old * (1 - 0.05) + 0.4 * 0.05
```

`topic_interferences[scene]` 与 `tone_preference[tone]` 同上。

### 2. 语言风格

| 字段 | 更新规则 |
|------|---------|
| `emoji_density` | 计算被选文案的 emoji 字符 / 总字符，EMA α=0.20 更新 |
| `sentence_length` | 计算被选文案平均句长，分 short/medium/long，one-hot EMA 更新 |
| `punctuation_pref` | 收集被选文案中出现的特殊标点（"！！"、"～"、"..."、"！？"），去重追加 |
| `fav_words` | 从被选文案抽 2-gram 高频词（频次 ≥2）+ 用户反馈关键词，去重追加，最多 30 个 |

### 3. feedback_history

每次反馈追加一条原始记录，最长保留 200 条；超出后丢弃最早的。

### 4. 时间衰减（手动触发）

```bash
python scripts/profile.py decay --factor 0.95
```

把全部数值字段按 factor（默认 0.95 = 衰减 5%）缩小；建议每月跑一次，或长期不活跃时跑。

### 5. 冷启动

首次使用时 `data/user_profile.json` 不存在，`load_profile()` 会返回默认值（所有数值字段 = 0.5，feedback_history=[]）。3-5 次反馈后画像开始稳定。

---

## 调用示例

### CLI

```bash
# 查看
python scripts/profile.py show

# JSON 输出
python scripts/profile.py show --json

# 反馈更新
python scripts/profile.py update --feedback '{
  "chosen_index": 2,
  "chosen_text": "家人们，雨后西湖真的氛围感拉满 🍃",
  "scene": "今天去了西湖",
  "platform": "xiaohongshu",
  "tone": "warm",
  "reason_keywords": ["emoji密集", "姐妹风"]
}'

# 追加 fav_words
python scripts/profile.py add-word --word "绝绝子" --word "yyds"

# 时间衰减
python scripts/profile.py decay --factor 0.95

# 重置
python scripts/profile.py reset
```

### Python

```python
from scripts.lib.schema import load_profile, save_profile
from pathlib import Path
import json

p = load_profile(Path("data/user_profile.json"))
print(p["language_style"]["fav_words"])
```

---

## 多用户支持

当前默认使用单个 `default` 用户。要支持多用户：

```bash
python scripts/profile.py --path data/alice.json show
python scripts/profile.py --path data/bob.json update --feedback '...'
```

或者修改 `load_profile()` 加 `user_id` 参数。**注意反馈调用的画像路径要与场景关联**。

---

## 隐私

- 画像文件**仅存在用户本地**（`data/` 下），不会被发到任何远端。
- 用户可随时 `reset` 或删除 `data/user_profile.json`。
- 若不希望保留画像，可把 `data/user_profile.json` 加入 `.gitignore`。