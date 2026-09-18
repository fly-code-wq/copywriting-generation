---
name: copygen
description: |
  Generates platform-tailored marketing/social copy from a user's scene description.
  Identifies user intent (platform / scene / tone / style), retrieves similar copy
  from a curated corpus, removes near-duplicates via SHA-256 + Levenshtein + n-gram
  Jaccard, and produces multiple innovative candidates with each platform's native
  voice (小红书 / 抖音 / 朋友圈 / 微博 / 知乎 / B站 / Twitter-X / Instagram).
  Builds and evolves a precise per-user profile from every selection so later copy
  progressively matches the user's voice. Use when the user mentions: 文案, 写文案,
  文案生成, 营销文案, 小红书文案, 抖音文案, 朋友圈文案, 微博文案, 知乎回答,
  B站动态, Twitter文案, Instagram文案, slogan, 标题, 种草文案, 创意写作,
  文案仿写, 文案改写, 文案润色, 文案优化, 文案创作, 文案库, 文案灵感,
  文案推荐, 文案生成器, 营销话术, 品牌文案, 广告文案, 短视频文案, 带货文案.
  Also matches when the user says things like: "帮我写条小红书", "我想发个朋友圈",
  "给这条视频配个标题", "帮我润色下文案", "写个slogan", "推文写一下".
  NOT for: 纯代码生成, 翻译任务, 文档摘要, 长篇报告写作, copy/paste binary file.
---

# 文案生成 Skill (copygen)

把"用户随口说的一句话场景"变成"符合平台调性的若干条原创文案"，并随用户的使用自动贴合用户语言风格。

## When to use this skill

用户在以下任意一种场景下，主动调用或被智能体自动触发：
- "我今天去了西湖，帮我写条小红书"
- "给这条抖音视频配个标题 + 文案"
- "我想发个朋友圈，高级感一点"
- "帮我想 5 个微博话题文案"
- "这是个新品，给我写几个 slogan"
- "这段文案太土了，帮我润色下"
- "写一个知乎开头，要专业但不要太严肃"

## Quick start (CLI)

```bash
# 生成
python scripts/copygen.py --scene "今天去了西湖，雨后空气特别好" --platform xiaohongshu --n 5

# 只做检索 + 去重（不输出 LLM 融合结果，便于调试）
python scripts/copygen.py --scene "今天去了西湖" --platform xiaohongshu --no-llm

# 反馈：用户选了第几条
python scripts/copygen.py --feedback '{"chosen_index": 2, "reason_keywords": ["emoji密集","姐妹风"]}'

# 查看用户画像
python scripts/copygen.py --show-profile

# 强制走联网检索补充文案
python scripts/copygen.py --scene "..." --platform xiaohongshu --web
```

## Workflow (智能体执行)

当本 skill 被触发后，智能体应严格按以下 9 步执行：

```
STEP 1  解析输入         → scene / platform / n / 反馈
STEP 2  意图识别         → 调 scripts/lib/intent.py，输出 platform/scene/tone/style
STEP 3  加载画像         → 读 data/user_profile.json，提取 language_style/platform_affinity 等
STEP 4  检索文案库       → scripts/search_corpus.py，取 Top-K（默认 K=3）
STEP 5  LLM 融合创新     → 智能体根据 references/fusion-method.md 的 hook-论据-CTA 三段式生成 n 条
STEP 7  相似度校验       → scripts/dedupe.py，过滤与库中/候选之间完全/高度雷同者
STEP 8  输出候选         → 给用户呈现 5 条文案 + 标签
STEP 9  记录反馈 + 入库  → 用户给出选择后，scripts/profile.py 更新画像；可选 scripts/init_corpus.py 把高赞候选入库
```

> STEP 6（图片配图等）非文本 skill 范围，按需扩展。

## Platform-specific notes

| 平台 | emoji 密度 | 字数 | 标签 | 钩子公式 | 参考文档 |
|------|----------|------|------|---------|---------|
| xiaohongshu | 高 | 300-800 | 3-5 个 # | 姐妹式 + 数字/反差 | references/platform-styles.md |
| douyin | 中 | 15-30（标题）| 极少 | 数字+结果 / 痛点+解决方案 | references/platform-styles.md |
| wechat_moments | 极低 | 30-100 | 无 | 文艺 + 留白 | references/platform-styles.md |
| weibo | 中 | ≥15 | 必带 # | 强情绪 + 蹭热点 | references/platform-styles.md |
| zhihu | 中 | 30-200（开头）| 极少 | 反常识 + 论据 + 立场 | references/platform-styles.md |
| bilibili | 中 | 20-100 | 话题 | 二次元 + 弹幕梗 | references/platform-styles.md |
| twitter | 低 | ≤280 | #+@ | 短促 + 立场 | references/platform-styles.md |
| instagram | 高 | 50-150 | # | emoji 堆 + 自拍文 | references/platform-styles.md |

完整风格卡见 `references/platform-styles.md`。

## Profile feedback loop

每次用户从候选里挑了一条并给出反馈关键词，`scripts/profile.py update` 会：
1. 把 `feedback_history` 追加一条；
2. 用 EMA α=0.15 更新 `platform_affinity` / `topic_interests` / `tone_preference`；
3. 从被选文案里抽取 `fav_words`，去重；
5. 7 天没使用的兴趣标签衰减 5%。

下次同样输入时，prompt 会带上画像摘要，生成的文案会更贴近用户口吻。

## Key references (按需加载)

- [references/intent-recognition.md](references/intent-recognition.md) — 平台/场景/情绪分类词典
- [references/platform-styles.md](references/platform-styles.md) — 8 平台风格卡
- [references/fusion-method.md](references/fusion-method.md) — hook-论据-CTA 三段式 + Few-shot 模板
- [references/user-profile-schema.md](references/user-profile-schema.md) — 画像 JSON Schema + 更新算法
- [references/corpus-format.md](references/corpus-format.md) — 文案库 JSONL 字段
- [references/web-search.md](references/web-search.md) — Tavily/WebFetch 联网 fallback
- [references/examples.md](references/examples.md) — 端到端调用示例

## Key scripts (确定性逻辑)

- [scripts/copygen.py](scripts/copygen.py) — 主入口 CLI
- [scripts/search_corpus.py](scripts/search_corpus.py) — 关键词 + Jaccard 检索
- [scripts/dedupe.py](scripts/dedupe.py) — SHA-256 + Levenshtein + n-gram 去重
- [scripts/profile.py](scripts/profile.py) — 画像读写 + EMA 更新
- [scripts/init_corpus.py](scripts/init_corpus.py) — 导入种子数据
- [scripts/web_search.py](scripts/web_search.py) — 可选联网检索

## Cross-agent compatibility

- **Claude Code**: 把整个目录软链到 `~/.claude/skills/copygen/` 或项目级 `.claude/skills/copygen/`
- **Codex CLI**: 软链到 `~/.codex/skills/copygen/` 或项目级 `.codex/skills/copygen/`
- **其他 Agent Skills 兼容智能体**: 把 `SKILL.md` 当 system prompt 片段加载，所有 CLI 都是 Python 标准库

> 安装示例（Windows PowerShell）：
> ```powershell
> New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\copygen" -Target "C:\Users\liuhong\Desktop\claude\temp_projects\text-generation"
> New-Item -ItemType Junction -Path "$env:USERPROFILE\.codex\skills\copygen" -Target "C:\Users\liuhong\Desktop\claude\temp_projects\text-generation"
> ```
> macOS/Linux：
> ```bash
> ln -s ~/Desktop/claude/temp_projects/text-generation ~/.claude/skills/copygen
> ln -s ~/Desktop/claude/temp_projects/text-generation ~/.codex/skills/copygen
> ```