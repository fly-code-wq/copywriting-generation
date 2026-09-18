"""候选去重：SHA-256 + Levenshtein + 3-gram Jaccard 三级流水线。

用法：
    python scripts/dedupe.py --candidates candidates.jsonl --against assets/seed_corpus.jsonl --out survivors.jsonl
    cat candidates.jsonl | python scripts/dedupe.py --stdin --json
    python scripts/dedupe.py --text "今天天气真好" --against assets/seed_corpus.jsonl

判定阈值：
- SHA 完全相等 → 重复
- 编辑距离 / 长度 ≤ 0.15 → 重复
- 3-gram Jaccard ≥ 0.70 → 重复
"""
from __future__ import annotations

import argparse
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
DEFAULT_CORPUS = SKILL_ROOT / "assets" / "seed_corpus.jsonl"

sys.path.insert(0, str(HERE))
from lib.similarity import (  # noqa: E402
    sha256_text,
    is_duplicate,
    similarity_score,
)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_jsonl_stream(stream) -> list[dict]:
    out: list[dict] = []
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _record_text(rec: dict | str) -> str:
    if isinstance(rec, str):
        return rec
    return rec.get("text") or rec.get("copy") or ""


def dedupe(
    candidates: list[dict | str],
    *,
    against: list[dict],
    edit_thresh: float = 0.40,
    jaccard_thresh: float = 0.55,
) -> dict:
    """对候选做去重。同时检查候选之间彼此不重复。

    Returns
    -------
    {
        "survivors": [dict],          # 通过的候选
        "removed":   [dict],          # 被去掉的，附 reason
        "stats":     {...}
    }
    """
    refs_text: list[str] = [_record_text(r) for r in against if _record_text(r)]
    ref_sha = {sha256_text(t) for t in refs_text}

    survivors: list[dict] = []
    removed: list[dict] = []
    seen_sha: set[str] = set()

    for cand in candidates:
        text = _record_text(cand)
        if not text:
            removed.append({"record": cand, "reason": "empty text"})
            continue

        sha = sha256_text(text)
        if sha in ref_sha or sha in seen_sha:
            removed.append({"record": cand, "reason": "sha256 hit (完全相同)"})
            continue
        seen_sha.add(sha)

        # 与参考库做相似度
        worst_score = None
        worst_reason = ""
        is_dup = False
        for ref_text in refs_text:
            dup, scores = is_duplicate(
                text, ref_text,
                edit_thresh=edit_thresh,
                jaccard_thresh=jaccard_thresh,
            )
            if dup:
                is_dup = True
                # 取最严重的指标作为 reason
                if scores.get("substring_dup"):
                    worst_reason = "candidate 是 reference 的子串"
                elif scores["sha_match"]:
                    worst_reason = "sha256 hit"
                elif scores["edit_norm"] <= edit_thresh:
                    worst_reason = f"edit_norm={scores['edit_norm']:.3f} <= {edit_thresh}"
                else:
                    worst_reason = f"3gram_jaccard={scores['jaccard']:.3f} >= {jaccard_thresh}"
                worst_score = scores
                break

        if is_dup:
            removed.append({
                "record": cand,
                "reason": worst_reason,
                "scores": worst_score,
            })
            continue

        survivors.append(cand if isinstance(cand, dict) else {"text": text})

    return {
        "survivors": survivors,
        "removed": removed,
        "stats": {
            "input": len(candidates),
            "survivors": len(survivors),
            "removed": len(removed),
            "against_refs": len(refs_text),
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="文案候选去重（SHA + Levenshtein + n-gram）")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--candidates", help="候选 JSONL 文件")
    src.add_argument("--stdin", action="store_true", help="从 stdin 读 JSONL")
    src.add_argument("--text", help="直接对单条文本判定")
    p.add_argument("--against", default=str(DEFAULT_CORPUS), help="参考库 JSONL")
    p.add_argument("--out", help="survivors 输出 JSONL（默认打印）")
    p.add_argument("--removed-out", help="removed 输出 JSONL（可选）")
    p.add_argument("--edit-thresh", type=float, default=0.40)
    p.add_argument("--jaccard-thresh", type=float, default=0.55)
    p.add_argument("--json", action="store_true", help="以 JSON 格式打印结果")
    args = p.parse_args(argv)

    # 收集候选
    if args.stdin:
        cands = read_jsonl_stream(sys.stdin)
    elif args.candidates:
        cands = load_jsonl(Path(args.candidates))
    else:
        cands = [{"text": args.text}]

    against = load_jsonl(Path(args.against))

    result = dedupe(
        cands,
        against=against,
        edit_thresh=args.edit_thresh,
        jaccard_thresh=args.jaccard_thresh,
    )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fout:
            for s in result["survivors"]:
                fout.write(json.dumps(s, ensure_ascii=False) + "\n")

    if args.removed_out:
        out_path = Path(args.removed_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fout:
            for s in result["removed"]:
                fout.write(json.dumps(s, ensure_ascii=False) + "\n")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    s = result["stats"]
    print(f"候选 {s['input']} 条，去重 {s['removed']} 条，幸存 {s['survivors']} 条（参考库 {s['against_refs']} 条）")
    for r in result["removed"]:
        text = _record_text(r["record"])[:60]
        print(f"  ✗ {r['reason']}  text={text}…")
    for s_ in result["survivors"]:
        text = _record_text(s_)[:80]
        print(f"  ✓ {text}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())