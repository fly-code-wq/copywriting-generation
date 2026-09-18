"""文本相似度计算工具 — 纯标准库，无第三方依赖。

提供：
- sha256_text(text) -> str: 文本指纹（去空白后）
- levenshtein(a, b) -> int: 编辑距离
- normalized_levenshtein(a, b) -> float: 归一化编辑距离，∈ [0, 1]
- ngrams(text, n=3) -> set: 字符 n-gram 集合
- jaccard(a_set, b_set) -> float: Jaccard 相似度
- tokenize_zh(text) -> list[str]: 简易中文分词（2-gram + 停用词过滤）
- similarity_score(a, b) -> dict: 汇总三路指标，给 dedupe.py 用
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

# 默认轻量停用词；如需更全可在调用方传入。
# 必须是 set / list 字面量，不能是单字符串（单字符串会被拆成单字符）
# 高频中文单字虚词（专门用于 2-gram 分词里"两个相邻字都是虚词就跳过"）
_SINGLE_CHAR_STOPWORDS = {
    "今", "明", "昨", "后", "前", "去", "来", "走", "回", "上", "下", "左", "右",
    "前", "后", "里", "外", "中", "内", "间", "旁",
    "的", "了", "着", "过", "在", "是", "也", "都", "还", "有", "又", "再", "并", "将",
    "不", "没", "无", "未", "别", "莫", "勿", "刚", "正", "才", "刚",
    "我", "你", "他", "她", "它", "们", "的", "之",
    "和", "与", "及", "而", "或", "但", "却", "则",
    "向", "从", "往", "到", "于", "为", "以", "因", "由", "对", "跟", "同", "把", "被", "让", "使", "给",
    "把", "被", "让", "使", "用", "做", "干",
    "想", "看", "听", "说", "话", "问", "答", "叫", "喊", "唱",
    "这", "那", "哪", "谁", "何", "怎", "为", "可", "能", "会", "要", "应", "须", "得", "该",
    "点", "分", "秒", "次", "回", "趟", "遍", "号", "第", "其", "某", "本", "此",
    "啊", "哎", "呀", "哇", "哦", "唉", "呢", "嗯", "哈", "嘛", "哒", "哟", "呵", "哼", "呸",
    "很", "挺", "太", "极", "最", "更", "非", "常",
    "与", "及", "或", "但", "而", "且", "并", "所",
}

_DEFAULT_STOPWORDS = {
    "的", "了", "着", "过", "在", "是", "也", "都", "还", "有", "又", "再",
    "被", "让", "使", "向", "从", "到", "以", "于", "和", "与", "及", "而",
    "或", "但", "就", "则", "之", "其", "此",
    "哪", "谁", "何", "不", "没", "无", "未", "很", "挺", "太", "极", "最", "更",
    "并", "将", "会", "要", "能", "可", "得", "才", "别", "莫", "勿",
    "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们", "自己", "大家",
    "今", "天", "明", "月", "年", "日", "时", "分", "秒", "点", "次", "回", "趟", "次", "遍", "回", "次", "号", "号", "第", "其", "某", "本", "上", "下", "左", "右", "前", "后", "里", "外", "中", "间", "今", "去", "来", "走", "进", "出", "做", "干", "想", "看", "听", "说", "话", "给", "把", "被", "让", "用", "到", "从", "往", "向", "为", "以", "因", "由", "对", "跟", "同", "和", "与", "及", "或", "但", "而", "且", "所", "这", "那", "哪", "谁", "何", "怎", "为", "可", "能", "会", "要", "应", "须", "须", "得", "该", "该", "非常",
    "啊", "哎", "呀", "哇", "哦", "唉", "呢", "嗯", "哈", "嘛", "哒", "哟", "呵", "哼", "呸",
    "所以", "因此", "但是", "如果", "虽然", "然而", "可是", "不过", "而且", "并且",
    "否则", "不然", "由于", "关于", "对于", "至于", "按照", "根据",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "百", "千", "万", "亿", "第一", "第二", "第三",
    "一些", "一点", "一点点", "两", "俩",
    "这里", "那里", "这些", "那些", "上面", "下面", "左边", "右边", "中间", "里面", "前面", "旁边",
    "今天", "明天", "昨天", "后天", "前天",
    "现在", "当时", "后来", "以后", "以前", "之前", "之后",
    "曾经", "已经", "正在", "即将", "刚刚",
    "什么", "怎么", "为什么", "如何", "哪里", "哪儿", "哪个", "几", "多少", "怎样", "这样",
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours",
    "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", "hers",
    "herself", "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing",
    "and", "but", "if", "or", "because", "as", "until", "while",
    "of", "at", "by", "for", "with", "about", "against", "between", "into", "through",
    "during", "before", "after", "above", "below", "to", "from", "up", "down", "in", "out",
    "on", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "s", "t", "can", "will", "just", "don", "should", "now",
}


def sha256_text(text: str) -> str:
    """文本指纹：去首尾空白、压缩中间空白，保证同"""
    norm = re.sub(r"\s+", "", text or "").strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _normalize_stopwords(stopwords: set[str] | list[str] | tuple[str, ...]) -> set[str]:
    """把"今天、明天、昨天" 这种顿号 / 逗号连接的元素展开成多个独立的 stopwords。

    支持元素之间使用 顿号 / 逗号 / 空格 / tab / 分号 / 竖线 分隔。
    """
    out: set[str] = set()
    for w in stopwords or []:
        if not w:
            continue
        for sep in ("、", ",", " ", "\t", ";", "|"):
            if sep in w:
                w = w.replace(sep, "|")
        for s in w.split("|"):
            s = s.strip()
            if s:
                out.add(s)
    return out


def levenshtein(a: str, b: str) -> int:
    """经典 DP 计算 Levenshtein 编辑距离。O(len(a)*len(b))。"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    # 使用单行优化版
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur.append(min(
                cur[-1] + 1,        # insert
                prev[j] + 1,        # delete
                prev[j - 1] + cost, # replace
            ))
        prev = cur
    return prev[-1]


def normalized_levenshtein(a: str, b: str) -> float:
    """归一化编辑距离：ed / max(len(a), len(b))。值越小越相似。"""
    if not a and not b:
        return 0.0
    m = max(len(a), len(b))
    if m == 0:
        return 0.0
    return levenshtein(a, b) / m


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    """字符 n-gram。中文友好；标点和空白不计入。"""
    if not text:
        return set()
    cleaned = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    if len(cleaned) < n:
        return {cleaned} if cleaned else set()
    return {cleaned[i : i + n] for i in range(len(cleaned) - n + 1)}


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """集合 Jaccard 相似度。|A∩B| / |A∪B|，值越大越相似。"""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def tokenize_zh(text: str, stopwords: set[str] | None = None) -> list[str]:
    """简易中文分词：
    - 先按非中文/字母/数字切
    - 中文部分做 2-gram 切
    - 英文/数字按整词
    - 过滤停用词
    适合文案检索场景，不适合严格要求分词精度的场景。
    """
    if not text:
        return []
    sw = stopwords if stopwords is not None else _DEFAULT_STOPWORDS
    tokens: list[str] = []

    # 按 unicode 范围遍历
    cur_zh: list[str] = []
    cur_en: list[str] = []

    def flush():
        zh = "".join(cur_zh)
        if len(zh) >= 2:
            for i in range(len(zh) - 1):
                t = zh[i : i + 2]
                if t not in sw:
                    tokens.append(t)
        cur_zh.clear()
        if cur_en:
            w = "".join(cur_en).lower()
            if w and w not in sw:
                tokens.append(w)
            cur_en.clear()

    for ch in text:
        if "一" <= ch <= "鿿":
            if cur_en:
                flush()
            cur_zh.append(ch)
        elif ch.isalnum():
            if cur_zh:
                flush()
            cur_en.append(ch)
        else:
            flush()
    flush()
    return tokens


def similarity_score(
    a: str,
    b: str,
    *,
    ngram_n: int = 3,
) -> dict:
    """给 dedupe.py 用的汇总指标。

    返回：
    - sha_match: 文本指纹是否完全一致
    - edit_norm: 归一化编辑距离 (越小越相似，0=完全相同)
    - jaccard:   3-gram Jaccard (越大越相似，1=完全相同)
    """
    a_clean = re.sub(r"\s+", "", a or "")
    b_clean = re.sub(r"\s+", "", b or "")
    return {
        "sha_match": sha256_text(a) == sha256_text(b),
        "sha_ngram_a": sha256_text(a),
        "sha256_b": sha256_text(b),
        "edit_norm": normalized_levenshtein(a_clean, b_clean),
        "jaccard": jaccard(_char_ngrams(a_clean, ngram_n), _char_ngrams(b_clean, ngram_n)),
    }


def is_duplicate(
    candidate: str,
    reference: str,
    *,
    edit_thresh: float = 0.15,
    jaccard_thresh: float = 0.70,
    ngram_n: int = 3,
) -> tuple[bool, dict]:
    """判定 candidate 是否与 reference 重复（任一指标超阈值即视为重复）。

    返回 (is_dup, scores)。
    """
    scores = similarity_score(candidate, reference, ngram_n=ngram_n)
    if scores["sha_match"]:
        return True, scores
    # 子串判定：candidate 是 reference 的子串（去空白）且比例 ≥ 0.35
    cand_clean = re.sub(r"\s+", "", candidate or "")
    ref_clean = re.sub(r"\s+", "", reference or "")
    if cand_clean and ref_clean and cand_clean in ref_clean and len(cand_clean) / len(ref_clean) >= 0.35:
        scores["substring_dup"] = True
        return True, scores
    if scores["edit_norm"] <= edit_thresh:
        return True, scores
    if scores["jaccard"] >= jaccard_thresh:
        return True, scores
    return False, scores


__all__ = [
    "sha256_text",
    "levenshtein",
    "normalized_levenshtein",
    "jaccard",
    "tokenize_zh",
    "similarity_score",
    "is_duplicate",
    "_char_ngrams",
]