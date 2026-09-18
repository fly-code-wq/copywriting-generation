"""copygen skill 的主入口 CLI。

把"场景描述 + 平台" → 检索本地文案库 → 输出 Top-K 参考素材 + 画像摘要 → 智能体据此融合 → 输出候选。
脚本只做"确定性"部分（意图识别、检索、去重、画像读写）；融合生成由 agent 自身完成。

用法：
    # 1) 生成素材（智能体拿到这串素材后做融合改写）
    python scripts/copygen.py --scene "今天去了西湖，雨后空气特别好" --platform xiaohongshu --n 5

    # 2) 仅做检索 + 去重，不输出 LLM 提示（--no-llm）
    python scripts/copygen.py --scene "今天去了西湖" --platform xiaohongshu --no-llm

    # 3) 反馈：用户选了第 N 条
    python scripts/copygen.py --feedback '{"chosen_index": 2, "chosen_text": "...", "scene": "今天去了西湖", "platform": "xiaohongshu"}'

    # 4) 查看画像
    python scripts/copygen.py --show-profile

    # 5) 把用户挑选的某条候选追加到文案库（可选）
    python scripts/copygen.py --append-to-corpus --text "新增文案" --platform xiaohongshu --scene travel

    # 6) 强制走联网补充素材
    python scripts/copygen.py --scene "..." --platform xiaohongshu --web
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent

sys.path.insert(0, str(HERE))

from lib.intent import recognize as recognize_intent  # noqa: E402
from lib.intent import extract_topic_keywords  # noqa: E402
from lib.schema import (  # noqa: E402
    PLATFORM_VALUES,
    SCENE_VALUES,
    default_profile,
    load_profile,
    save_profile,
    validate_corpus_record,
    now_iso,
)
from lib.similarity import sha256_text  # noqa: E402

from search_corpus import search as search_corpus  # noqa: E402
from dedupe import dedupe, load_jsonl  # noqa: E402
import profile as profile_mod  # noqa: E402
import web_search as web_search_mod  # noqa: E402


def _assets_dir() -> Path:
    return SKILL_ROOT / "assets"


def _corpus_path() -> Path:
    return _assets_dir() / "seed_corpus.jsonl"


def _profile_path() -> Path:
    return SKILL_ROOT / "data" / "user_profile.json"


def _format_profile_summary(p: dict) -> str:
    """生成一段画像摘要，便于塞进 prompt。"""
    lines = []
    fav = p.get("language_style", {}).get("fav_words", [])[:8]
    if fav:
        lines.append(f"用户偏好词：{'、'.join(fav)}")
    em = p.get("language_style", {}).get("emoji_density", 0.5)
    lines.append(f"emoji 密度倾向：{em:.2f}（0=不用，1=密集）")
    sl = p.get("language_style", {}).get("sentence_length", "medium")
    lines.append(f"句长倾向：{sl}")
    pa = p.get("platform_affinity", {})
    if pa:
        top_plat = sorted(pa.items(), key=lambda x: -x[1])[:3]
        lines.append("常用平台 TOP3：" + "、".join(f"{k}({v:.2f})" for k, v in top_plat))
    ti = p.get("topic_interests", {})
    if ti:
        top_scene = sorted(ti.items(), key=lambda x: -x[1])[:3]
        lines.append("兴趣场景 TOP3：" + "、".join(f"{k}({v:.2f})" for k, v in top_scene))
    return "\n".join(lines)


def _append_to_corpus(args, text: str, platform: str, scene: str, tags: list[str] | None = None) -> dict:
    """把一条新文案追加到种子库。"""
    path = _corpus_path()
    if not text or platform not in PLATFORM_VALUES:
        return {"ok": False, "reason": "missing text or invalid platform"}
    if scene not in SCENE_VALUES:
        scene = "other"

    # 生成 id
    existing_ids = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line.strip())
                if "id" in rec:
                    existing_ids.add(rec["id"])
            except Exception:
                pass
    n = 1
    while f"user_{n:04d}" in existing_ids:
        n += 1
    new_id = f"user_{n:04d}"

    rec = {
        "id": new_id,
        "platform": platform,
        "scene": scene,
        "text": text.strip(),
        "tags": tags or [],
        "created_at": now_iso(),
    }
    ok, errs = validate_corpus_record(rec)
    if not ok:
        return {"ok": False, "errors": errs}

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fout:
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True, "id": new_id}


# ─────────────── 主流程 ──────────────────────────────

def cmd_generate(args: argparse.Namespace) -> int:
    scene_text: str = args.scene or ""
    if not scene_text:
        print("[ERR] --scene 必填", file=sys.stderr)
        return 2

    profile_path = Path(args.profile)
    p = load_profile(profile_path)

    intent = recognize_intent(
        scene_text,
        assets_dir=_assets_dir(),
        explicit_platform=args.platform,
    )

    # 若用户显式传了 platform，覆盖
    if args.platform:
        intent["platform"] = args.platform

    # 检索本地库
    top_k = max(args.n * 3, 6)
    retrieved = search_corpus(
        scene_text,
        top_k=top_k,
        platform=intent.get("platform") or None,
        scene=intent.get("scene") or None,
        corpus_path=_corpus_path(),
        assets_dir=_assets_dir(),
    )

    # 可选联网
    web_hits = []
    if args.web:
        q = " ".join([
            intent.get("platform", ""),
            intent.get("scene", ""),
            intent.get("tone", ""),
            scene_text,
        ]).strip()
        web_hits = web_search_mod.search_web(q, top_k=5, provider=args.web_provider)

    # 摘要
    profile_summary = _format_profile_summary(p)

    output = {
        "intent": intent,
        "user_profile_summary": profile_summary,
        "retrieved": retrieved,
        "web_hits": web_hits,
        "n_requested": args.n,
        "platform": intent.get("platform") or args.platform,
        "scene": intent.get("scene") or "other",
        "tone": intent.get("tone") or "",
        "style": intent.get("style") or "",
        "topic_keywords": extract_topic_keywords(scene_text, top_k=5),
        "hint": (
            "智能体请根据 references/fusion-method.md 的 hook-论据-CTA 三段式，"
            "结合 user_profile_summary 与 retrieved 候选，融合生成 n 条原创文案，"
            f"保证不与 retrieved 中任意一条相似度过高。然后用 scripts/dedupe.py 校验。"
        ),
    }

    if args.json or args.no_llm:
        # --no-llm 仍然输出完整素材供智能体调用；--json 让 stdout 是 JSON
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    # 人类可读
    print("=" * 70)
    print(f"📝 场景：{scene_text}")
    print(f"🎯 意图识别：platform={intent['platform']}  scene={intent['scene']}  "
          f"tone={intent['tone']}  style={intent['style']}  confidence={intent['confidence']}")
    print(f"👤 用户画像摘要：\n{profile_summary}")
    print("=" * 70)
    print(f"\n🔍 本地库参考 ({len(retrieved)} 条)：")
    for i, r in enumerate(retrieved, 1):
        print(f"\n  [{i}] id={r['id']}  platform={r['platform']}  scene={r['scene']}  score={r['score']}")
        print(f"      tags={r['tags']}  tone={r['tone']}  style={r['style']}")
        print(f"      text: {r['text']}")

    if web_hits:
        print(f"\n🌐 联网补充 ({len(web_hits)} 条)：")
        for i, r in enumerate(web_hits, 1):
            print(f"  [{i}] {r['title']}")
            if r.get("url"):
                print(f"      {r['url']}")
            print(f"      {r['snippet'][:160]}")

    print("\n" + "=" * 70)
    print("✨ 下一步：智能体根据 references/fusion-method.md 融合生成 "
          f"{args.n} 条候选文案（platform={intent.get('platform') or args.platform}）")
    print("    生成后用 scripts/dedupe.py 校验去重，最后输出给用户。")
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    """记录用户反馈，更新画像。"""
    if not args.feedback:
        print("[ERR] --feedback 必填（JSON 字符串）", file=sys.stderr)
        return 2

    fb = json.loads(args.feedback)
    fb.setdefault("scene", "")
    fb.setdefault("platform", "")

    # 调 profile.py update 子命令
    profile_args = argparse.Namespace(path=args.profile, feedback=args.feedback)
    rc = profile_mod.cmd_update(profile_args)
    if rc != 0:
        return rc

    # 可选：把被选文案入库
    if args.also_add and fb.get("chosen_text"):
        added = _append_to_corpus(
            args,
            text=fb["chosen_text"],
            platform=fb.get("platform", "weibo"),
            scene=fb.get("scene", "other"),
            tags=fb.get("reason_keywords", []),
        )
        if added.get("ok"):
            print(f"  → 已把被选文案追加到文案库 (id={added['id']})")
        else:
            print(f"  → 追加文案失败: {added}", file=sys.stderr)

    return 0


def cmd_show_profile(args: argparse.Namespace) -> int:
    a = argparse.Namespace(path=args.profile, json=args.json)
    return profile_mod.cmd_show(a)


def cmd_append(args: argparse.Namespace) -> int:
    if not args.text or not args.platform:
        print("[ERR] --text 和 --platform 必填", file=sys.stderr)
        return 2
    scene = args.scene or "other"
    if scene not in SCENE_VALUES:
        scene = "other"
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    added = _append_to_corpus(args, args.text, args.platform, scene, tags)
    print(json.dumps(added, ensure_ascii=False, indent=2))
    return 0 if added.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="copygen 文案生成 skill 主入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--profile", default=str(_profile_path()), help="用户画像路径")

    # 生成
    g = p.add_argument_group("生成")
    g.add_argument("--scene", help="用户场景描述")
    g.add_argument("--platform", choices=sorted(list(PLATFORM_VALUES) + [""]), help="目标平台")
    g.add_argument("--n", type=int, default=5, help="要生成的候选条数")
    g.add_argument("--web", action="store_true", help="是否额外走联网检索")
    g.add_argument("--web-provider", choices=["auto", "tavily", "webfetch"], default="auto")
    g.add_argument("--no-llm", action="store_true", help="只输出检索素材与画像，智能体不参与生成")

    # 反馈
    f = p.add_argument_group("反馈 / 画像")
    f.add_argument("--feedback", help="用户反馈 JSON")
    f.add_argument("--also-add", action="store_true", help="反馈时同时把被选文案追加到文案库")
    f.add_argument("--show-profile", action="store_true", help="打印用户画像后退出")

    # 入库
    a = p.add_argument_group("追加文案到种子库")
    a.add_argument("--append-to-corpus", action="store_true", dest="append_to_corpus",
                   help="追加一条新文案")
    a.add_argument("--text", help="要追加的文案内容")
    a.add_argument("--scene-name", dest="scene", default="other", help="场景")
    a.add_argument("--tags", help="标签，逗号分隔")

    # 输出
    o = p.add_argument_group("输出")
    o.add_argument("--json", action="store_true", help="JSON 输出")

    args = p.parse_args(argv)

    # 互斥路由
    if args.show_profile:
        return cmd_show_profile(args)
    if args.feedback:
        return cmd_feedback(args)
    if args.append_to_corpus:
        return cmd_append(args)
    if args.scene:
        return cmd_generate(args)

    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())