"""文案库与用户画像的 JSON Schema 定义 + 校验工具。

这里采用 JSON Schema Draft-07 的子集，仅做基本字段类型校验，不引入 jsonschema 依赖。
所有校验函数返回 (ok: bool, errors: list[str])。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

# ─────────────── 文案库 JSONL schema ───────────────────────────
# 每条文案记录的必填字段、可选字段、合法枚举值。

PLATFORM_VALUES: set[str] = {
    "xiaohongshu", "douyin", "wechat_moments",
    "weibo", "zhihu", "bilibili",
    "twitter", "instagram",
}
SCENE_VALUES: set[str] = {
    "travel", "food", "fashion", "lifestyle",
    "tech", "beauty", "fitness", "parenting",
    "work", "study", "emotion", "other",
}
TONE_VALUES: set[str] = {"warm", "humor", "luxury", "energetic", "calm", "ironic", "professional"}
STYLE_VALUES: set[str] = {"种草", "测评", "教程", "打卡", "vlog", "吐槽", "科普", "情感", "带货", "段子"}

CORPUS_REQUIRED_FIELDS = ("id", "platform", "scene", "text")
CORPUS_OPTIONAL_FIELDS = ("tags", "tone", "style", "source", "created_at")


def validate_corpus_record(rec: dict[str, Any]) -> tuple[bool, list[str]]:
    """校验单条文案库记录。"""
    errs: list[str] = []
    for k in CORPUS_REQUIRED_FIELDS:
        if k not in rec:
            errs.append(f"missing required field: {k}")
    if "platform" in rec and rec["platform"] not in PLATFORM_VALUES:
        errs.append(f"invalid platform: {rec['platform']!r}, expect one of {sorted(PLATFORM_VALUES)}")
    if "scene" in rec and rec["scene"] not in SCENE_VALUES:
        # not scene-matched
        errs.append(f"invalid scene: {rec['scene']!r}, expect one of {sorted(SCENE_VALUES)}")
    if "tone" in rec and rec["tone"] not in TONE_VALUES:
        errs.append(f"invalid tone: {rec['tone']!r}")
    if "style" in rec and rec["style"] not in STYLE_VALUES:
        errs.append(f"invalid style: {rec['style']!r}")
    if "text" in rec and not isinstance(rec["text"], str):
        errs.append("text must be string")
    if "text" in rec and len(rec.get("text", "")) == 0:
        errs.append("text is empty")
    return (len(errs) == 0, errs)


# ─────────────── 用户画像 schema ───────────────────────────────

PROFILE_DEFAULT: dict[str, Any] = {
    "user_id": "default",
    "version": 1,
    "created_at": "",
    "updated_at": "",
    "demographics": {
        "age_range": "",
        "gender_guess": "",
        "region_guess": "",
    },
    "language_style": {
        "emoji_density": 0.5,           # 0~1
        "punctuation_pref": [],         # 例：["！！", "～", "..."]
        "sentence_length": "medium",    # short / medium / long
        "fav_words": [],                # 常用词 / 网络词
    },
    "platform_affinity": {             # 各平台偏好 0~1
        "xiaohongshu": 0.5,
        "douyin": 0.5,
        "wechat_moments": 0.5,
        "weibo": 0.5,
        "zhihu": 0.5,
        "bilibili": 0.5,
        "twitter": 0.5,
        "instagram": 0.5,
    },
    "topic_interests": {               # 各场景兴趣 0~1
        "travel": 0.5, "food": 0.5, "fashion": 0.5, "lifestyle": 0.5,
        "tech": 0.5, "beauty": 0.5, "fitness": 0.5, "parenting": 0.5,
        "work": 0.5, "study": 0.5, "emotion": 0.5, "other": 0.5,
    },
    "tone_preference": {               # 情绪倾向
        "warm": 0.5, "humor": 0.5, "luxury": 0.5,
        "energetic": 0.5, "calm": 0.5, "ironic": 0.5, "professional": 0.5,
    },
    "feedback_history": [],            # list[dict]
}


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def default_profile(user_id: str = "default") -> dict[str, Any]:
    import copy
    p = copy.deepcopy(PROFILE_DEFAULT)
    ts = now_iso()
    p["user_id"] = user_id
    p["created_at"] = ts
    p["updated_at"] = ts
    return p


def validate_profile(p: dict[str, Any]) -> tuple[bool, list[str]]:
    """基本字段完整性校验，不强制所有字典键都存在（允许增量）。"""
    errs: list[str] = []
    for k in ("user_id", "version", "language_style", "feedback_history"):
        if k not in p:
            errs.append(f"missing field: {k}")
    if "platform_affinity" in p and not isinstance(p["platform_affinity"], dict):
        errs.append("platform_affinity must be dict")
    if "topic_interests" in p and not isinstance(p["topic_interests"], dict):
        errs.append("topic_interests must be dict")
    if "tone_preference" in p and not isinstance(p["tone_preference"], dict):
        errs.append("tone_preference must be dict")
    return (len(errs) == 0, errs)


def load_profile(path: Path) -> dict[str, Any]:
    """读取画像 JSON；不存在则返回默认画像（不写盘）。"""
    import json
    if not path.exists():
        return default_profile()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # 合并默认值（容错）
        merged = default_profile(data.get("user_id", "default"))
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        return merged
    except Exception:
        return default_profile()


def save_profile(p: dict[str, Any], path: Path) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    p["updated_at"] = now_iso()
    path.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = [
    "PLATFORM_VALUES", "SCENE_VALUES", "TONE_VALUES", "STYLE_VALUES",
    "CORPUS_REQUIRED_FIELDS", "CORPUS_OPTIONAL_FIELDS",
    "validate_corpus_record",
    "PROFILE_DEFAULT", "default_profile", "validate_profile",
    "load_profile", "save_profile", "now_iso",
]