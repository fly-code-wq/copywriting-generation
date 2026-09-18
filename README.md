# copygen — 标准文案生成 Skill

一个跨 Claude Code / Codex / 其他 Agent Skills 标准智能体的**标准化文案生成 skill**。

> 用户随口说一句话场景 → 智能体识别意图 → 检索本地文案库 → 融合交叉创新 → 去重 → 输出多平台候选；用户的选择会反哺用户画像，下个发出来的命中文案会更贴合用户口吻。

## 目录结构

```
text-generation/
├── SKILL.md                   # skill 入口（YAML frontmatter + 6 步工作流）
├── README.md                  # 本文件
├── scripts/
│   ├── copygen.py             # 主入口 CLI（生成 / 反馈 / 查看画像）
│   ├── search_corpus.py       # 文案库检索
│   ├── dedupe.py              # 候选去重（SHA-256 + Levenshtein + n-gram）
│   ├── profile.py             # 用户画像读写 + EMA 更新
│   ├── init_corpus.py         # 导入种子数据
│   ├── web_search.py          # 可选联网检索
│   └── lib/
│       ├── similarity.py      # 文本相似度算法
│       ├── schema.py          # 文案 / 画像 JSON Schema
│       └── intent.py          # 意图识别
├── references/
│   ├── intent-recognition.md
│   ├── platform-styles.md
│   ├── fusion-method.md
│   ├── user-profile-schema.md
│   ├── corpus-format.md
│   ├── web-search.md
│   └── examples.md
├── assets/
│   ├── seed_corpus.jsonl      # 预置 100 条种子文案
│   ├── platform_keywords.json
│   └── stopwords_zh.txt
└── data/
    └── user_profile.json      # 运行时生成
```

## 安装

零依赖（Python 3.8+ 标准库）。

### Claude Code

```bash
# 项目级
ln -s "$(pwd)" .claude/skills/copygen

# 或用户级
ln -s "$(pwd)" ~/.claude/skills/copygen
```

### Codex CLI

```bash
ln -s "$(pwd)" ~/.codex/skills/copygen
# 或
ln -s "$(pwd)" .codex/skills/copygen
```

### Windows PowerShell

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\copygen" -Target "$pwd"
New-Item -ItemType Junction -Path "$env:USERPROFILE\.codex\skills\copygen" -Target "$pwd"
```

### 其他 Agent Skills 标准智能体

把整个目录放到它们约定的扫描路径下即可（如 `~/.copilot/skills/`、`~/.cursor/skills/` 等）。

## 快速使用

### 1. 生成（无智能体，直接跑脚本看素材）

```bash
python scripts/copygen.py --scene "今天去了西湖，雨后空气特别好" \
  --platform xiaohongshu --n 5 --no-llm
```

会输出意图识别结果、用户画像摘要、Top-5 检索候选。

### 2. 在 Claude Code / Codex 中使用

直接对话：

> "我今天去了西湖，帮我写条小红书"

Claude 加载 `copygen` skill 后会按 `SKILL.md` 的 6 步流程执行：
1. 意图识别
2. 加载画像
3. 检索文案库
4. 智能体融合生成
5. 去重校验
6. 输出 5 条候选

### 3. 用户反馈，更新画像

```bash
python scripts/copygen.py --feedback '{
  "chosen_index": 2,
  "chosen_text": "家人们，雨后西湖真的氛围感拉满 🍃...",
  "scene": "今天去了西湖",
  "platform": "xiaohongshu",
  "tone": "warm",
  "reason_keywords": ["emoji密集", "姐妹风"]
}'
```

画像会更新 `platform_affinity` / `topic_interests` / `tone_preference` / `fav_words`。

### 4. 查看画像

```bash
python scripts/copygen.py --show-profile
# 或 JSON
python scripts/copygen.py --show-profile --json
```

### 5. 联网补充（可选）

需要 Tavily API key：
```bash
export TAVILY_API_KEY="tvly-xxxx"
python scripts/copygen.py --scene "..." --platform xiaohongshu --web
```

或装 `tavily-python`：
```bash
pip install tavily-python
```

### 6. 导入自己的文案库

```bash
# JSONL
python scripts/init_corpus.py --from my_corpus.jsonl

# CSV
python scripts/init_corpus.py --from my_corpus.csv
```

## 工作流

```
STEP 1  解析输入         → scene / platform / n / 反馈
STEP 2  意图识别         → scripts/lib/intent.py
STEP 3  加载画像         → data/user_profile.json
STEP 4  检索文案库       → scripts/search_corpus.py
STEP 5  LLM 融合创新     → 智能体按 references/fusion-method.md
STEP 6  相似度校验       → scripts/dedupe.py
STEP 7  输出候选         → 给用户
STEP 8  记录反馈 + 入库  → scripts/profile.py
```

详见 [SKILL.md](SKILL.md)。

## 支持的平台

| 平台 | key |
|------|-----|
| 小红书 | `xiaohongshu` |
| 抖音 | `douyin` |
| 朋友圈 | `wechat_moments` |
| 微博 | `weibo` |
| 知乎 | `zhihu` |
| B站 | `bilibili` |
| Twitter-X | `twitter` |
| Instagram | `instagram` |

每个平台的 emoji 密度、字数、标签、钩子公式见 [references/platform-styles.md](references/platform-styles.md)。

## 用户画像维度

- 基础属性（age_range / gender_guess / region_guess）
- 语言风格（emoji_density / punctuation_pref / sentence_length / fav_words）
- 平台偏好（8 平台 0~1 分布）
- 场景兴趣（12 场景 0~1 分布）
- 情绪倾向（7 种 tone 0~1 分布）
- feedback_history（最近 200 条原始记录）

更新算法：EMA α=0.15 + 时间衰减（手动触发）。

详见 [references/user-profile-schema.md](references/user-profile-schema.md)。

## 依赖

- **Python 3.8+**（标准库）
- 可选：`tavily-python`（联网检索）

无需其他第三方包。

## 端到端验证

```bash
# 1. 检索
python scripts/search_corpus.py --query "西湖 旅行" --top 3

# 2. 画像初始化
python scripts/copygen.py --show-profile

# 3. 模拟用户反馈
python scripts/copygen.py --feedback '{"chosen_index":1,"chosen_text":"家人们，雨后西湖真的氛围感拉满 🍃","scene":"今天去了西湖","platform":"xiaohongshu","tone":"warm","reason_keywords":["emoji密集"]}'

# 4. 再次查看画像（应已变化）
python scripts/copygen.py --show-profile

# 5. 去重校验
echo '{"text":"家人们谁懂啊，雨后西湖真的氛围感拉满"}' > /tmp/test.jsonl
python scripts/dedupe.py --candidates /tmp/test.jsonl --against assets/seed_corpus.jsonl
```

## 扩展

### 加新平台

1. 在 `assets/platform_keywords.json` 加别名：
   ```json
   "pinterest": {"aliases": ["pinterest", "图钉"], "weight": 1.0}
   ```
2. 在 `scripts/lib/schema.py` 的 `PLATFORM_VALUES` 加 `"pinterest"`
3. 在 `references/platform-styles.md` 写一份风格卡
4. 在文案库里加几条种子

### 加新场景

1. 在 `platform_keywords.json` 的 `scene` 加类别
2. 在 `schema.py` 的 `SCENE_VALUES` 加 key
3. 在 `user_profile.topic_interests` 默认值加 key

### 加新 tone

类似上面。

## 许可

MIT