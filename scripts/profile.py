"""用户画像管理。

子命令：
    show                         打印当前画像
    update --feedback JSON       根据用户反馈更新画像
    reset                        重置为默认画像
    add-word --word 词           手动往 fav_words 追加
    decay [--days N]             对所有数值字段做时间衰减

更新算法：
    - EMA α=0.15 更新 platform_affinity / topic_interests / tone_preference
    - feedback_history 追加原始记录
    - fav_words：被选文案里出现的高频词去重后追加（按频率排序）
    - emoji_density：被选文案的 emoji 数 / 字符数，EMA 更新
    - sentence_length：短(<30字) / 中(30-80) / 长(>80) one-hot 更新
    - 7 天没出现的数值字段衰减 5%（仅 decay 子命令触发）

用法：
    python scripts/profile.py show
    python scripts/profile.py update --feedback '{"chosen_index":2,"reason_keywords":["emoji密集"]}'
    python scripts/profile.py add-word --word "绝绝子"
    python scripts/profile.py decay
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
DEFAULT_PROFILE = SKILL_ROOT / "data" / "user_profile.json"

sys.path.insert(0, str(HERE))
from lib.schema import (  # noqa: E402
    default_profile,
    load_profile,
    save_profile,
    validate_profile,
    now_iso,
)


# ───────────── 辅助：分析一条文案 ──────────────────────────────

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "☀-⛿"
    "✀-➿"
    "]+",
    flags=re.UNICODE,
)
STOPWORDS_FEED = set(
    "的了是在也和有与及而或但就都还又再把被给让对此向从到以中与与及之"
    "啊哦呢吧嘛呀呵哈唉嗨嗯"
    "the a an and or but to of in for is are am be do does did"
)
PLATFORM_VALUES = (
    "xiaohongshu", "douyin", "wechat_moments",
    "weibo", "zhihu", "bilibili",
    "twitter", "instagram",
)
SCENE_VALUES = (
    "travel", "food", "fashion", "lifestyle",
    "tech", "beauty", "fitness", "parenting",
    "work", "study", "emotion", "other",
)
TONE_VALUES = (
    "warm", "humor", "luxury", "energetic", "calm", "ironic", "professional",
)


def analyze_text(text: str) -> dict[str, Any]:
    """从一条文案里抽取画像信号。"""
    if not text:
        return {}
    chars = len(text)
    emojis = EMOJI_RE.findall(text)
    emoji_density = len("".join(emojis)) / chars if chars else 0.0

    # 句长（按换行或句末标点切）
    sentences = [s for s in re.split(r"[。！？!?\n]+", text) if s.strip()]
    avg_len = chars / max(len(sentences), 1)
    if avg_len < 30:
        sl = "short"
    elif avg_len < 80:
        sl = "medium"
    else:
        sl = "long"

    # 高频词（2-gram）
    grams: dict[str, int] = {}
    for i in range(len(text) - 1):
        a, b = text[i], text[i + 1]
        if "一" <= a <= "鿿" and "一" <= b <= "鿿":
            g = a + b
            if g not in STOPWORDS_FEED:
                grams[g] = grams.get(g, 0) + 1
    fav = [w for w, c in sorted(grams.items(), key=lambda kv: -kv[1]) if c >= 2][:10]

    # 标点偏好
    punct: list[str] = []
    for p in ("！！", "～", "~", "...", "…", "??", "！？", "！?"):
        if p in text:
            punct.append(p)

    return {
        "emoji_density": emoji_density,
        "sentence_length": sl,
        "fav_words": fav,
        "punctuation_pref": punct,
    }


def _ema_update(d: dict[str, float], key: str, target: float, alpha: float = 0.15) -> None:
    """EMA 更新：new = old*(1-α) + target*α。值钳制在 [0, 1]。"""
    cur = float(d.get(key, 0.5))
    new = cur * (1 - alpha) + target * alpha
    d[key] = round(max(0.0, min(1.0, new)), 4)


# ───────────── 子命令实现 ───────────────────────────────

def cmd_show(args: argparse.Namespace) -> int:
    p = load_profile(Path(args.path))
    if args.json:
        print(json.dumps(p, ensure_ascii=False, indent=2))
    else:
        print(f"--- User Profile ({p.get('user_id','default')}) v{p.get('version',1)} ---")
        print(f"updated_at: {p.get('updated_at')}")
        print(f"demographics: {p.get('demographics', {})}")
        print(f"language_style: {p.get('language_style', {})}")
        print(f"platform_affinity:")
        for k, v in sorted(p.get("platform_affinity", {}).items(), key=lambda x: -x[1]):
            print(f"  - {k}: {v}")
        print(f"topic_interests:")
        for k, v in sorted(p.get("topic_interests", {}).items(), key=lambda x: -x[1]):
            print(f"  - {k}: {v}")
        print(f"tone_preference:")
        for k, v in sorted(p.get("tone_preference", {}).items(), key=lambda x: -x[1]):
            print(f"  - {k}: {v}")
        print(f"feedback_history: {len(p.get('feedback_history', []))} 条")
        if p.get("feedback_history"):
            print("  最近 3 条：")
            for h in p["feedback_history"][-3:]:
                print(f"    - {h.get('ts')} scene={h.get('scene')!r} chosen={h.get('chosen_index')} reason={h.get('reason_keywords')}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """根据用户反馈更新画像。

    feedback JSON 字段：
        chosen_index: int             # 用户选的索引（必填）
        chosen_text: str              # 被选文案的完整文字（强烈建议带，便于抽词）
        candidates: list[str]         # 候选列表（可选）
        scene: str                    # 场景描述
        platform: str                 # 平台
        tone: str                     # 智能体识别出的 tone（可选）
        style: str                    # 智能体识别出的 style（可选）
        reason_keywords: list[str]    # 用户给出的反馈关键词
    """
    path = Path(args.path)
    p = load_profile(path)

    try:
        fb = json.loads(args.feedback) if args.feedback else {}
    except json.JSONDecodeError as e:
        print(f"[ERR] feedback JSON 解析失败: {e}", file=sys.stderr)
        return 2

    chosen_text: str = fb.get("chosen_text", "")
    platform: str = fb.get("platform", "")
    scene: str = fb.get("scene", "")
    tone: str = fb.get("tone", "")
    chosen_idx: int = int(fb.get("chosen_index", -1))

    # 若 scene 不是合法枚举值，自动调意图识别
    if scene and scene not in SCENE_VALUES:
        try:
            from lib.intent import recognize as _recognize
            assets_dir = path.parent.parent / "assets" if path.parent.name == "data" else path.parent / "assets"
            intent = _recognize(scene, assets_dir=assets_dir if assets_dir.exists() else None,
                                explicit_platform=platform if platform in PLATFORM_VALUES else None)
            scene = intent.get("scene") or scene
            if not tone:
                tone = intent.get("tone") or ""
        except Exception:
            pass

    signals = analyze_text(chosen_text) if chosen_text else {}

    # 1. EMA 更新平台亲和度
    if platform in PLATFORM_VALUES:
        _ema_update(p["platform_affinity"], platform, 1.0)
        # 其他平台轻微衰减（降到 0.4 附近）
        for other in PLATFORM_VALUES:
            if other != platform:
                _ema_update(p["platform_affinity"], other, 0.4, alpha=0.05)

    # 2. EMA 更新场景兴趣
    if scene in SCENE_VALUES:
        _ema_update(p["topic_interests"], scene, 1.0)
        for other in SCENE_VALUES:
            if other != scene:
                _ema_update(p["topic_interests"], other, 0.4, alpha=0.05)

    # 3. EMA 更新情绪倾向
    if tone in TONE_VALUES:
        _ema_update(p["tone_preference"], tone, 1.0)
        for other in TONE_VALUES:
            if other != tone:
                _ema_update(p["tone_preference"], other, 0.4, alpha=0.05)

    # 4. 语言风格
    if signals.get("emoji_density") is not None:
        _ema_update(p["language_style"], "emoji_density", signals["emoji_density"], alpha=0.20)

    if signals.get("sentence_length"):
        # one-hot 更新三个字段
        cur = p["language_style"].setdefault("sentence_length_pref", {"short": 0.33, "medium": 0.34, "long": 0.33})
        for k in cur:
            cur[k] = cur[k] * 0.85
        cur[signals["sentence_length"]] = round(cur.get(signals["sentence_length"], 0.0) + 0.15, 4)
        p["language_style"]["sentence_length"] = max(cur, key=cur.get)

    if signals.get("punctuation_pref"):
        pref: list[str] = p["language_style"].get("punctuation_pref", [])
        for pn in signals["punctuation_pref"]:
            if pn not in pref:
                pref.append(pn)
        p["language_style"]["punctuation_pref"] = pref[:10]

    # 5. fav_words：合并（被选文案高频词 + 用户反馈关键词）
    if signals.get("fav_words"):
        fav: list[str] = p["language_style"].get("fav_words", [])
        existing_set = set(fav)
        for w in signals["fav_words"]:
            if w not in existing_set:
                fav.append(w)
                existing_set.add(w)
        p["language_style"]["fav_words"] = fav[:30]

    if (rk := fb.get("reason_keywords")):
        fav = p["language_style"].setdefault("fav_words", [])
        es = set(fav)
        for w in rk:
            if w and w not in es:
                fav.append(w)
                es.add(w)
        p["language_style"]["fav_words"] = fav[:30]

    # 6. feedback_history
    history = p.setdefault("feedback_history", [])
    history.append({
        "ts": now_iso(),
        "scene": fb.get("scene", ""),
        "platform": platform,
        "tone": tone,
        "style": fb.get("style", ""),
        "chosen_index": chosen_idx,
        "reason_keywords": fb.get("reason_keywords", []),
        "chosen_text_preview": (chosen_text[:80] + "…") if chosen_text and len(chosen_text) > 80 else chosen_text,
    })
    # 仅保留最近 200 条
    p["feedback_history"] = history[-200:]

    p["version"] = p.get("version", 1) + 1

    ok, errs = validate_profile(p)
    if not ok:
        print(f"[WARN] 画像校验未通过: {errs}", file=sys.stderr)

    save_profile(p, path)
    print(f"画像已更新 -> {path} (v{p['version']})")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    p = default_profile(args.user_id or "default")
    save_profile(p, Path(args.path))
    print(f"已重置 -> {args.path}")
    return 0


def cmd_add_word(args: argparse.Namespace) -> int:
    path = Path(args.path)
    p = load_profile(path)
    fav = p["language_style"].setdefault("fav_words", [])
    for w in (args.word or []):
        if w not in fav:
            fav.append(w)
    p["language_style"]["fav_words"] = fav[:30]
    p["version"] = p.get("version", 1) + 1
    save_profile(p, path)
    print(f"已追加 fav_words: {args.word}")
    return 0


def cmd_decay(args: argparse.Namespace) -> int:
    """对所有数值画像做时间衰减。"""
    path = Path(args.path)
    p = load_profile(path)
    factor = float(args.factor)
    for k in ("platform_affinity", "topic_interests", "tone_preference"):
        for sub, v in p.get(k, {}).items():
            p[k][sub] = round(float(v) * factor, 4)
    p["version"] = p.get("version", 1) + 1
    save_profile(p, path)
    print(f"已对全部数值字段按 factor={factor} 衰减")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="用户画像读写")
    p.add_argument("--path", default=str(DEFAULT_PROFILE), help="画像文件路径")
    sub_p = p.add_subparsers(dest="cmd", required=True)

    sp_show = sub_p.add_parser("show", help="查看画像")
    sp_show.add_argument("--json", action="store_true")
    sp_show.set_defaults(func=cmd_show)

    sp_up = sub_p.add_parser("update", help="根据反馈更新画像")
    sp_up.add_argument("--feedback", required=True, help="JSON 字符串")
    sp_up.set_defaults(func=cmd_update)

    sp_rst = sub_p.add_parser("reset", help="重置画像")
    sp_rst.add_argument("--user-id", dest="user_id", default="default")
    sp_rst.set_defaults(func=cmd_reset)

    sp_aw = sub_p.add_parser("add-word", help="追加 fav_words")
    sp_aw.add_argument("--word", action="append", required=True)
    sp_aw.set_defaults(func=cmd_add_word)

    sp_dc = sub_p.add_parser("decay", help="数值字段时间衰减")
    sp_dc.add_argument("--factor", type=float, default=0.95,
                       help="乘数，默认 0.95 (= 衰减 5%)")
    sp_dc.set_defaults(func=cmd_decay)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())