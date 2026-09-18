"""意图识别辅助库。

输入：用户场景描述（一句话）
输出：{platform, scene, tone, style, confidence, raw_keywords}

实现方式：
1. 优先使用 assets/platform_keywords.json（用户可扩展）；
2. 否则回退到内置默认词典；
3. 评分 = 关键词命中数 × 权重。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# 内置默认词典（兜底）
DEFAULT_KEYWORDS: dict[str, dict[str, Any]] = {
    "platform": {
        "xiaohongshu":     {"aliases": ["小红书", "xhs", "red", "种草", "姐妹"],        "weight": 1.0},
        "douyin":          {"aliases": ["抖音", "dy", "tiktok", "短视频", "口播"],       "weight": 1.0},
        "wechat_moments":  {"aliases": ["朋友圈", "好友圈", "发圈"],                    "weight": 1.0},
        "weibo":           {"aliases": ["微博", "weibo", "热搜"],                       "weight": 1.0},
        "zhihu":           {"aliases": ["知乎", "zhihu"],                               "weight": 1.0},
        "bilibili":        {"aliases": ["b站", "b 站", "bilibili", "哔哩哔哩", "小破站"], "weight": 1.0},
        "twitter":         {"aliases": ["twitter", "推特", "x 平台", "x平台"],          "weight": 1.0},
        "instagram":       {"aliases": ["instagram", "ins", "IG"],                     "weight": 1.0},
    },
    "scene": {
        "travel":    {"aliases": ["旅行", "出游", "旅游", "出行", "打卡", "景点", "西湖", "度假", "自驾"], "weight": 1.0},
        "food":      {"aliases": ["美食", "吃", "探店", "餐厅", "夜宵", "下午茶", "咖啡", "甜品", "奶茶"], "weight": 1.0},
        "fashion":   {"aliases": ["穿搭", "搭配", "ootd", "秋冬", "春夏", "单品", "上新", "限量"],     "weight": 1.0},
        "lifestyle": {"aliases": ["生活", "日常", "家居", "vlog", "周末", "仪式感"],                   "weight": 1.0},
        "tech":      {"aliases": ["数码", "测评", "开箱", "新机", "手机", "电脑", "耳机"],              "weight": 1.0},
        "beauty":    {"aliases": ["护肤", "彩妆", "口红", "粉底", "面膜", "医美"],                    "weight": 1.0},
        "fitness":   {"aliases": ["健身", "跑步", "瑜伽", "撸铁", "减肥", "塑形"],                    "weight": 1.0},
        "parenting": {"aliases": ["宝宝", "娃", "育儿", "母婴", "亲子", "幼儿园"],                    "weight": 1.0},
        "work":      {"aliases": ["上班", "打工", "加班", "述职", "汇报", "客户"],                     "weight": 1.0},
        "study":     {"aliases": ["考研", "考证", "学习", "备考", "期末"],                              "weight": 1.0},
        "emotion":   {"aliases": ["emo", "治愈", "伤感", "心情", "感悟", "回忆"],                       "weight": 1.0},
    },
    "tone": {
        "warm":         {"aliases": ["温暖", "治愈", "暖心", "温柔"],                   "weight": 1.0},
        "humor":        {"aliases": ["搞笑", "段子", "好玩", "逗"],                      "weight": 1.0},
        "luxury":       {"aliases": ["高级", "精致", "轻奢", "高级感"],                   "weight": 1.0},
        "energetic":    {"aliases": ["燃", "炸", "爆", "热血", "热血沸腾"],              "weight": 1.0},
        "calm":         {"aliases": ["安静", "宁静", "岁月静好", "平淡"],                 "weight": 1.0},
        "ironic":       {"aliases": ["吐槽", "反讽", "阴阳怪气"],                        "weight": 1.0},
        "professional": {"aliases": ["专业", "理性", "严肃", "深度"],                    "weight": 1.0},
    },
    "style": {
        "种草": {"aliases": ["种草", "安利", "推荐", "好物"],   "weight": 1.0},
        "测评": {"aliases": ["测评", "评测", "体验"],          "weight": 1.0},
        "教程": {"aliases": ["教程", "攻略", "指南", "怎么"],   "weight": 1.0},
        "打卡": {"aliases": ["打卡", "vlog", "记录"],          "weight": 1.0},
        "吐槽": {"aliases": ["吐槽", "避雷", "拔草"],          "weight": 1.0},
        "科普": {"aliases": ["科普", "涨知识", "原理"],        "weight": 1.0},
        "情感": {"aliases": ["情感", "感悟", "故事"],          "weight": 1.0},
        "带货": {"aliases": ["带货", "直播间", "优惠"],        "weight": 1.0},
        "段子": {"aliases": ["段子", "梗", "玩梗"],            "weight": 1.0},
    },
}


_KEYWORDS_CACHE: dict[str, dict[str, Any]] | None = None


def _load_keywords(assets_dir: Path | None) -> dict[str, dict[str, Any]]:
    """优先读 assets/platform_keywords.json；失败回退到默认。"""
    global _KEYWORDS_CACHE
    if _KEYWORDS_CACHE is not None:
        return _KEYWORDS_CACHE
    if assets_dir is not None:
        kw_path = assets_dir / "platform_keywords.json"
        if kw_path.exists():
            try:
                _KEYWORDS_CACHE = json.loads(kw_path.read_text(encoding="utf-8"))
                return _KEYWORDS_CACHE
            except Exception:
                pass
    _KEYWORDS_CACHE = DEFAULT_KEYWORDS
    return _KEYWORDS_CACHE


def _score_category(
    text: str,
    category: dict[str, dict[str, Any]],
) -> tuple[str, float, list[str]]:
    """在单个分类下挑出命中分数最高的 value。"""
    best_key, best_score, hits = "", 0.0, []
    text_lower = text.lower()
    for key, conf in category.items():
        aliases = conf.get("aliases", []) or []
        weight = float(conf.get("weight", 1.0))
        score = 0
        local_hits = []
        for alias in aliases:
            n = text_lower.count(alias.lower())
            if n > 0:
                score += n
                local_hits.append(alias)
        score *= weight
        if score > best_score:
            best_key, best_score, hits = key, score, local_hits
    return best_key, best_score, hits


def recognize(
    text: str,
    *,
    assets_dir: Path | None = None,
    explicit_platform: str | None = None,
) -> dict[str, Any]:
    """主入口。

    Args:
        text: 用户的场景描述
        assets_dir: skill 内 assets 目录路径
        explicit_platform: 用户命令行显式传入的 platform（优先于自动识别）
    """
    if not text:
        return {"platform": "", "scene": "", "tone": "", "style": "",
                "confidence": 0.0, "raw_keywords": {}}

    kw = _load_keywords(assets_dir)

    platform, p_score, p_hits = _score_category(text, kw.get("platform", {}))
    scene,    s_score, s_hits = _score_category(text, kw.get("scene", {}))
    tone,     t_score, t_hits = _score_category(text, kw.get("tone", {}))
    style,    st_score, st_hits = _score_category(text, kw.get("style", {}))

    if explicit_platform and explicit_platform in (kw.get("platform") or {}):
        platform = explicit_platform
        p_score = max(p_score, 1.0)  # 显式传值视为高置信

    # confidence：归一化为 0~1
    total = p_score + s_score + t_score + st_score
    confidence = min(1.0, total / 6.0)

    return {
        "platform": platform,
        "scene": scene,
        "tone": tone,
        "style": style,
        "confidence": round(confidence, 3),
        "raw_keywords": {
            "platform": p_hits,
            "scene": s_hits,
            "tone": t_hits,
            "style": st_hits,
        },
    }


def extract_topic_keywords(text: str, top_k: int = 5) -> list[str]:
    """从场景描述里抽 2~4 字关键短语，用于检索时拼接。

    策略：
    1. 中文 2-gram：过滤停用词 + 单字停用词开头 / 结尾 + 在界面已出现在关键词词典里优先
    3. 英文/数字整词：>=2 字符
    """
    from .similarity import _DEFAULT_STOPWORDS, _normalize_stopwords, _SINGLE_CHAR_STOPWORDS
    text = text or ""
    sw = _normalize_stopwords(_DEFAULT_STOPWORDS)
    sc = _SINGLE_CHAR_STOPWORDS

    # 收集"含中文"的字符作为词边界
    grams: dict[str, int] = {}
    i = 0
    while i < len(text) - 1:
        a, b = text[i], text[i + 1]
        if "一" <= a <= "鿿" and "一" <= b <= "鿿":
            g = a + b
            # 任何一边是单字停用词就跳过
            if a in sc or b in sc or a in sw or b in sw:
                i += 1
                continue
            grams[g] = grams.get(g, 0) + 1
        i += 1

    # 抽英文/数字整词
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    for w in words:
        if len(w) >= 2 and w not in sw:
            grams[w] = grams.get(w, 0) + 1

    # 加分：出现在关键词词典里的 2-gram 提到前面
    kw_match = set()
    for cat in DEFAULT_KEYWORDS.values():
        for conf in cat.values():
            for alias in conf.get("aliases", []):
                if 2 <= len(alias) <= 4 and alias in text:
                    kw_match.add(alias)
    for w in kw_match:
        grams[w] = grams.get(w, 0) + 5  # 关键词加权

    sorted_items = sorted(grams.items(), key=lambda kv: (-kv[1], -len(kv[0])))

    # 后置过滤：扔掉两个字符都包含在 sw 的 2-gram
    out: list[str] = []
    for w, _ in sorted_items:
        if len(w) == 2 and (all(ch in sc for ch in w) or all(ch in sw for ch in w)):
            continue
        out.append(w)
        if len(out) >= top_k:
            break
    return out


def _tokenize_zh(text: str, stopwords: set[str] | None = None) -> list[str]:
    """简易中文分词（被 label 吸收在 lib/similarity.py 里，这里加一个本地 alias）。"""
    from .similarity import tokenize_zh, _normalize_stopwords, _DEFAULT_STOPWORDS
    sw = _normalize_stopwords(stopwords if stopwords is not None else _DEFAULT_STOPWORDS)
    return tokenize_zh(text, stopwords=sw)


__all__ = [
    "DEFAULT_KEYWORDS",
    "recognize",
    "extract_topic_keywords",
]