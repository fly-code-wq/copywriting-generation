# 文案库格式 (corpus-format.md)

文案库用 **JSONL**（一行一条 JSON）存储，便于追加、git diff、跨平台。

默认文件：`assets/seed_corpus.jsonl`（skill 内置种子库）。

## 字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 唯一标识，建议格式 `prefix_NNNN`（如 `xhs_0001`） |
| `platform` | string | ✅ | 平台枚举，见下表 |
| `scene` | string | ✅ | 场景枚举，见下表 |
| `text` | string | ✅ | 文案正文（≥1 字） |
| `tags` | array[string] |  | 标签（用于检索匹配） |
| `tone` | string |  | 情绪基调 |
| `style` | string |  | 内容类型 |
| `source` | string |  | 来源 URL / 平台 / 作者 |
| `created_at` | string |  | ISO 时间戳 |

## 枚举值

### platform（8 个）

```
xiaohongshu      小红书
douyin           抖音
wechat_moments   朋友圈
weibo            微博
zhihu            知乎
bilibili         B站
twitter          Twitter-X
instagram        Instagram
```

### scene（12 个）

```
travel       旅行
food         美食
fashion      时尚穿搭
lifestyle    生活方式
tech         数码科技
beauty       美妆护肤
fitness      健身运动
parenting    母婴亲子
work         职场工作
study        学习备考
emotion      情感感悟
other        其它
```

### tone

```
warm / humor / luxury / energetic / calm / ironic / professional
```

### style

```
种草 / 测评 / 教程 / 打卡 / vlog / 吐槽 / 科普 / 情感 / 带货 / 段子
```

## JSONL 示例

```jsonl
{"id":"xhs_0001","platform":"xiaohongshu","scene":"travel","text":"雨后的西湖真的太治愈了 🍃\n站在断桥上听雨声……","tags":["西湖","旅行","治愈"],"tone":"warm","style":"打卡","created_at":"2026-09-01"}
{"id":"xhs_0002","platform":"xiaohongshu","scene":"food","text":"这家藏在巷子里的咖啡店绝了 ☕️","tags":["咖啡","探店"],"tone":"warm","style":"种草"}
{"id":"dy_0001","platform":"douyin","scene":"travel","text":"月薪5千也能去！西湖3天只要800","tags":["西湖","攻略"],"tone":"energetic","style":"教程"}
{"id":"wb_0001","platform":"weibo","scene":"emotion","text":"emo了，今天又是打工的一天","tags":["打工人"],"tone":"ironic","style":"段子"}
```

## 校验

用 `scripts/init_corpus.py --info` 看统计：

```bash
python scripts/init_corpus.py --info
```

输出：
```
assets/seed_corpus.jsonl: 100 条
  - xiaohongshu: 25
  - douyin: 20
  - wechat_moments: 15
  - weibo: 15
  - zhihu: 10
  - bilibili: 5
  - twitter: 5
  - instagram: 5
```

用 `python scripts/init_corpus.py --from your.jsonl` 校验 + 导入：

```bash
python scripts/init_corpus.py --from my_corpus.jsonl
# 导入 50 条，跳过 2 条，错误 0 条 -> assets/seed_corpus.jsonl
#   ! line 3: invalid platform: 'red'
```

## 导入方式

### 从 JSONL 导入（推荐）

```bash
python scripts/init_corpus.py --from my.jsonl
python scripts/init_corpus.py --from my.jsonl --append   # 追加而非覆盖
```

### 从 CSV 导入

```bash
python scripts/init_corpus.py --from my.csv
# 列名自动识别：
#   text / content / copy / 文案 / 正文 / 标题
#   platform / 平台
#   scene / 场景 / 类目
#   tags / 标签 / 关键词
#   tone / 语气
#   style / 风格 / 类型

# 也可显式指定列名
python scripts/init_corpus.py --from my.csv \
  --text-col content --platform-col platform --scene-col category \
  --tags-col tags --tone-col tone --style-col style
```

CSV 里写"小红书"会**自动**映射到 `xiaohongshu`。

### 手动追加一条

```bash
python scripts/copygen.py --append-to-corpus \
  --text "今天去了西湖，氛围感拉满 🍃" \
  --platform xiaohongshu --scene-name travel --tags "西湖,旅行,氛围感"
```

## 检索

```bash
python scripts/search_corpus.py --query "西湖 旅行" --top 5
python scripts/search_corpus.py --query "西湖 旅行" --platform xiaohongshu --top 3
python scripts/search_corpus.py --query "美食 探店" --scene food --json
```

## 数据规模建议

| 规模 | 检索方式 | 性能 |
|------|---------|------|
| < 500 条 | 当前 2-gram + Jaccard | 毫秒级 |
| 500 - 10k | 当前 2-gram + Jaccard | < 100ms |
| 10k - 100k | 升级到 BM25 或 TF-IDF | 需引入倒排索引库 |
| > 100k | 向量数据库（chromadb / milvus / qdrant） | 需引入 embedding |

MVP 阶段推荐 < 500 条种子 + 用户反馈时增量追加。

## 去重

新增文案前先跑 `scripts/dedupe.py`：

```bash
echo '{"text":"新增文案"}' > new.jsonl
python scripts/dedupe.py --candidates new.jsonl --against assets/seed_corpus.jsonl
# 默认阈值 edit-thresh=0.40, jaccard-thresh=0.55（可在 -h 中调整）
```