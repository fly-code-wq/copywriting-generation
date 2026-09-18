"""文案库检索：基于 2-gram + jaccard + 关键词命中加权。

支持 platform / scene 过滤；返回 Top-K。

用法：
    python scripts/search_corpus.py --query "西湖 旅行" --top 5
    python scripts/search_corpus.py --query "美食 探店" --platform douyin --top 3
    python scripts/search_corpus.py --query "..." --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 让 Windows 终端能正确打印中文 + emoji
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
DEFAULT_CORPUS = SKILL_ROOT / "assets" / "seed_corpus.jsonl"

sys.path.insert(0, str(HERE))
from lib.intent import extract_topic_keywords  # noqa: E402
from lib.similarity import tokenize_zh, _normalize_stopwords  # noqa: E402


def load_corpus(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as fin:
        for ln, line in enumerate(fin, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                rec["_line"] = ln
                records.append(rec)
            except json.JSONDecodeError:
                continue
    return records


def _load_stopwords(assets_dir: Path) -> set[str]:
    p = assets_dir / "stopwords_zh.txt"
    if not p.exists():
        return set()
    out: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.add(line)
    return _normalize_stopwords(out)


def _score_record(
    query_tokens: set[str],
    query_topics: list[str],
    rec: dict,
    weights: dict,
) -> float:
    """综合评分：text jaccard * 0.55 + tags 命中 * 0.20 + scene 命中 * 0.15 + topic 命中 * 0.10"""
    text = rec.get("text", "")
    text_tokens = set(tokenize_zh(text))
    if not query_tokens or not text_tokens:
        jac = 0.0
    else:
        jac = len(query_tokens & text_tokens) / len(query_tokens | text_tokens)

    tags = set(rec.get("tags", []) or [])
    tag_hit = sum(1 for t in query_topics if t in tags or t in text)

    scene_hit = 0.0
    if rec.get("scene") in {"other"}:
        scene_hit = 0.5
    # query_topics 是短语；与 scene 直接匹配权重更高
    if any(kw in rec.get("scene", "") for kw in query_topics):
        scene_hit = 1.0

    # topic 命中：query_topics 直接出现在 text 里
    text_lc = text.lower()
    topic_hit = sum(1 for t in query_topics if t.lower() in text_lc) / max(len(query_topics), 1)

    return (
        jac * weights["text_jaccard"]
        + tag_hit * weights["tag_hit"]
        + scene_hit * weights["scene_hit"]
        + topic_hit * weights["topic_hit"]
    )


def search(
    query: str,
    *,
    top_k: int = 5,
    platform: str | None = None,
    scene: str | None = None,
    corpus_path: Path = DEFAULT_CORPUS,
    assets_dir: Path | None = None,
) -> list[dict]:
    assets_dir = assets_dir or corpus_path.parent.parent
    stopwords = _load_stopwords(assets_dir)
    records = load_corpus(corpus_path)
    if not records:
        return []

    query_tokens = set(tokenize_zh(query, stopwords=stopwords))
    query_topics = extract_topic_keywords(query, top_k=5)

    weights = {
        "text_jaccard": 0.55,
        "tag_hit": 0.20,
        "scene_hit": 0.15,
        "topic_hit": 0.10,
    }

    scored: list[tuple[float, dict]] = []
    for rec in records:
        if platform and rec.get("platform") != platform:
            continue
        if scene and rec.get("scene") != scene:
            continue
        s = _score_record(query_tokens, query_topics, rec, weights)
        if s > 0:
            scored.append((s, rec))

    scored.sort(key=lambda x: (-x[0], x[1].get("id", "")))

    # 如果 platform/scene 过滤后不足 top_k，放宽过滤再补一次
    if platform or scene:
        if len(scored) < top_k:
            for rec in records:
                if rec in [r for _, r in scored]:
                    continue
                s = _score_record(query_tokens, query_topics, rec, weights)
                if s > 0:
                    scored.append((s, rec))
            scored.sort(key=lambda x: (-x[0], x[1].get("id", "")))

    out = []
    for s, rec in scored[:top_k]:
        out.append({
            "id": rec.get("id"),
            "platform": rec.get("platform"),
            "scene": rec.get("scene"),
            "tags": rec.get("tags", []),
            "tone": rec.get("tone", ""),
            "style": rec.get("style", ""),
            "text": rec.get("text", ""),
            "score": round(s, 4),
        })
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="文案库检索")
    p.add_argument("--query", required=True, help="场景描述/关键词")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--platform", default=None, help="按平台过滤")
    p.add_argument("--scene", default=None, help="按场景过滤")
    p.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    p.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = p.parse_args(argv)

    results = search(
        args.query,
        top_k=args.top,
        platform=args.platform,
        scene=args.scene,
        corpus_path=Path(args.corpus),
    )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    if not results:
        print(f"[WARN] 文案库为空或无命中（{Path(args.corpus)}）")
        return 1

    print(f"=== 检索结果（query={args.query!r}, top={args.top}）===")
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] id={r['id']}  platform={r['platform']}  scene={r['scene']}  score={r['score']}")
        print(f"    tags={r['tags']}  tone={r['tone']}  style={r['style']}")
        print(f"    text: {r['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())