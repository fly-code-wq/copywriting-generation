# 端到端调用示例 (examples.md)

从"用户一句话"到"输出候选 + 画像更新"的完整链路。

---

## 示例 1：基本生成（小红书旅行）

### 用户输入
> "今天去了西湖，雨后空气特别好，帮我写条小红书"

### 智能体执行（按 SKILL.md Workflow）

```bash
# STEP 1 + 2: 解析输入 + 意图识别
python -c "
from scripts.lib.intent import recognize
import json
print(json.dumps(recognize('今天去了西湖，雨后空气特别好，帮我写条小红书',
  assets_dir=__import__('pathlib').Path('assets')), ensure_ascii=False, indent=2))
"
# → {
#     "platform": "xiaohongshu",
#     "scene": "travel",
#     "tone": "warm",
#     "style": "打卡",
#     "confidence": 0.83
#   }

# STEP 3 + 4: 加载画像 + 检索文案库
python scripts/copygen.py --scene "今天去了西湖，雨后空气特别好" \
  --platform xiaohongshu --n 5 --no-llm --json
```

### 输出（片段）

```json
{
  "intent": {
    "platform": "xiaohongshu",
    "scene": "travel",
    "tone": "warm",
    "style": "打卡",
    "confidence": 0.83
  },
  "user_profile_summary": "用户偏好词：暂无；emoji 密度倾向：0.50；句长倾向：medium",
  "retrieved": [
    {
      "id": "xhs_0001",
      "platform": "xiaohongshu",
      "scene": "travel",
      "tags": ["西湖", "旅行", "治愈"],
      "tone": "warm",
      "style": "打卡",
      "text": "雨后的西湖真的太治愈了 🍃\n站在断桥上听雨声，整个人都安静下来…",
      "score": 0.85
    },
    ...
  ],
  "topic_keywords": ["西湖", "雨后", "空气", "去了"],
  "hint": "智能体请根据 references/fusion-method.md ... 生成 n 条原创文案"
}
```

### 智能体融合生成（按 fusion-method.md）

读 `retrieved` 中 Top-3，按 hook / body / CTA 拆解，交叉重组：

```
[1] Hook: "雨后的西湖真的太治愈了 🍃"
    Body: 站在断桥上听雨声 / 雨滴打在荷叶上
    CTA:  📍 杭州西湖 · 断桥 + 标签
```

套到当前场景，输出 5 条候选（mock）：

```
[1] 家人们谁懂啊！雨后西湖真的氛围感拉满 🍃
    站在断桥上，空气里都是夏天的味道
    📍 杭州西湖 · 断桥
    #西湖 #杭州旅行 #氛围感 #治愈系风景 #周末去哪儿

[2] 上周刚去西湖！5 个雨后超出片机位分享
    北山街 / 杨公堤 / 茅家埠 / 苏堤 / 浴鹄湾
    #西湖拍照机位 #雨后西湖 #小众旅行地

[3] 谁懂啊，雨后 30 分钟的西湖直接绝绝子 ✨
    黄金时间窗，氛围感拉满
    #西湖旅行 #氛围感 #2024最新

[4] 西湖雨后实拍 🍃🌧️
    这空气，这氛围，谁来谁知道
    #治愈系 #慢生活 #杭州

[5] 月薪 5 千也能去！雨后西湖 1 日游攻略 🌧️
    断桥 → 茅家埠 → 杨公堤
    #攻略 #西湖 #杭州旅行
```

### 去重校验

```bash
echo '[{"text":"家人们谁懂啊！雨后西湖真的氛围感拉满 🍃"},...]' > candidates.jsonl
python scripts/dedupe.py --candidates candidates.jsonl \
  --against assets/seed_corpus.jsonl --out survivors.jsonl
```

如果某条与 seed 库中某条 3-gram Jaccard ≥ 0.7，会被剔除；其它通过。

---

## 示例 2：用户反馈 + 画像进化

### 用户选择

> 用户选第 3 条"谁懂啊，雨后 30 分钟的西湖直接绝绝子 ✨"，反馈"我喜欢 emoji 多的，喜欢'绝绝子'这种词"

### 智能体执行

```bash
python scripts/copygen.py --feedback '{
  "chosen_index": 3,
  "chosen_text": "谁懂啊，雨后 30 分钟的西湖直接绝绝子 ✨\n黄金时间窗，氛围感拉满\n#西湖旅行 #氛围感 #2024最新",
  "scene": "今天去了西湖",
  "platform": "xiaohongshu",
  "tone": "warm",
  "style": "打卡",
  "reason_keywords": ["emoji密集", "绝绝子", "姐妹风"]
}' --also-add
```

### 内部 update 逻辑

| 字段 | 变化 |
|------|------|
| `platform_affinity.xiaohongshu` | 0.5 → 0.575（EMA α=0.15，target=1.0） |
| `platform_affinity.douyin` | 0.5 → 0.495（轻微负向） |
| `topic_interests.travel` | 0.5 → 0.575 |
| `tone_preference.warm` | 0.5 → 0.575 |
| `language_style.emoji_density` | 0.5 → 0.575（实际 emoji 占比） |
| `language_style.sentence_length` | medium → short（被选文案平均 < 30 字） |
| `language_style.fav_words` | `+ ["绝绝子", "谁懂", "氛围"]` |
| `feedback_history` | +1 条 |
| `version` | 1 → 2 |

### 同时把被选文案入库

```bash
# 上面 --also-add 触发
python scripts/copygen.py --append-to-corpus \
  --text "谁懂啊，雨后 30 分钟的西湖直接绝绝子 ✨ ..." \
  --platform xiaohongshu --scene-name travel \
  --tags "西湖,绝绝子,氛围感"
```

`data/user_profile.json` 与 `assets/seed_corpus.jsonl` 同时更新。

### 二次输入同样场景

```bash
python scripts/copygen.py --scene "今天又去了西湖" \
  --platform xiaohongshu --n 5 --no-llm --json
```

`user_profile_summary` 现在是：
```
用户偏好词：绝绝子、谁懂、氛围
emoji 密度倾向：0.58
句长倾向：short
常用平台 TOP3：xiaohongshu(0.58)、douyin(0.49)、wechat_moments(0.49)
兴趣场景 TOP3：travel(0.58)、food(0.49)、fashion(0.49)
```

智能体据此生成的文案**会更短、emoji 更多、含"绝绝子""谁懂"等词**。

---

## 示例 3：朋友圈高级感文案

### 用户输入
> "我想发个朋友圈，高级感一点，不要 emoji"

### CLI

```bash
python scripts/copygen.py --scene "今天去了西湖" \
  --platform wechat_moments --n 5 --no-llm
```

### 意图识别

```json
{"platform":"wechat_moments","scene":"travel","tone":"luxury","style":"情感","confidence":0.7}
```

### 智能体融合（按 platform-styles.md 朋友圈规则）

```
emoji_density ≈ 0.1
字数 30-100
无标签
钩子公式：文艺+留白
```

候选：
```
[1] 雨后的西湖，安静得像一幅画。
    人少，空气里有荷叶的味道。

[2] 断桥边，雨刚停。
    没有游客，没有喧闹。

[4] 西湖不需要滤镜。
    雨天，更真实。

[5] 慢一点。
    这才是杭州。
```

---

## 示例 4：抖音标题

### 用户输入
> "帮这条旅行视频配个抖音标题"

### CLI

```bash
python scripts/copygen.py --scene "西湖 旅行" \
  --platform douyin --n 5
```

### 候选

```
[1] 月薪 5 千也能去！西湖 3 天只要 800
[2] 99% 的人都玩错了！西湖 5 月最该来的地方
[3] 千万别周末去！西湖避雷攻略
[4] 别再问西湖怎么玩！这篇直接收藏
[5] 西湖下雨天直接封神 🌧️
```

每个都用了抖音的钩子公式（数字+结果 / 痛点+解决方案 / 反差+悬念）。

---

## 示例 5：润色旧文案

### 用户输入
> "这段文案太土了，帮我润色：今天天气真好，我去西湖玩了一圈"

### 智能体执行

1. 意图识别：scene=travel，platform=xiaohongshu（默认）
2. 用 `references/fusion-method.md` 的"反向工程"流程：先把原句拆 hook+body+CTA
3. 重新组合 + 平台风格对齐 + 用户画像注入

### 输出

```
[1] 🍃 雨后的西湖，氛围感直接拉满！
    站在断桥上，空气是甜的。
#西湖旅行 #氛围感

[2] 谁懂啊，西湖一下雨就封神 ✨
    建议收藏这条笔记
#西湖 #杭州旅行 #治愈系风景

[4] 月薪 5 千也能去！西湖雨天超出片
#西湖 #拍照机位 #小众旅行
```

---

## 示例 6：联动 web_search 联网补充

```bash
python scripts/copygen.py --scene "西湖 旅行 秋天" \
  --platform xiaohongshu --n 5 --web
```

如果本地库"秋天西湖"覆盖不足，会调 `scripts/web_search.py` 拿联网结果。

---

## 示例 7：批量数据导入

### 把用户 CSV 导进文案库

```bash
python scripts/init_corpus.py --from data/user_corpus.csv
# CSV 列：text, platform, scene, tags, tone, style
```

### 把被选文案自动入库

```bash
python scripts/copygen.py --feedback '{
  "chosen_index": 1,
  "chosen_text": "...",
  "platform": "xiaohongshu"
}' --also-add
```

---

## 示例 8：跨智能体使用

### Claude Code

把整个目录软链到 `~/.claude/skills/copygen/`，触发方式：
- 用户输入"帮我写条小红书" → 自动触发
- 或 `/copygen --scene "..." --platform ...`

### Codex CLI

软链到 `~/.codex/skills/copygen/`；触发：
- 模型自动识别
- 或 `$copygen --scene "..." --platform ...`

### 自定义 Agent

加载 `SKILL.md` 作为 system prompt 片段；agent 自己执行其中的 CLI 命令。