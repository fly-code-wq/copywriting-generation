"""从 JSONL / CSV 导入文案到内置文案库。

用法：
    python scripts/init_corpus.py --from assets/seed_corpus.jsonl
    python scripts/init_corpus.py --from data/my_corpus.csv --text-col content --platform-col platform
    python scripts/init_corpus.py --append assets/seed_corpus.jsonl    # 追加而非覆盖

默认目标文件：assets/seed_corpus.jsonl （skill 内置种子库）
可加 --target data/my_corpus.jsonl 自定义。

CSV 列名自动识别常见别名：
    text / content / copy / 文案 / 正文
    platform / 平台
    scene / 场景
    tags / 标签 / 关键词
    tone / 语气
    style / 风格 / 类型
"""
from __future__ import annotations

import argparse
import csv
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
DEFAULT_TARGET = SKILL_ROOT / "assets" / "seed_corpus.jsonl"

# 让 scripts/lib/ 可被 import
sys.path.insert(0, str(HERE))
from lib.schema import (
    validate_corpus_record,
    PLATFORM_VALUES,
    SCENE_VALUES,
    STYLE_VALUES,
)


TEXT_COL_ALIASES = ("text", "content", "copy", "文案", "正文", "标题")
PLATFORM_COL_ALIASES = ("platform", "platform_id", "平台")
SCENE_COL_ALIASES = ("scene", "topic", "category", "场景", "类目")
TAGS_COL_ALIASES = ("tags", "keywords", "标签", "关键词")
TONE_COL_ALIASES = ("tone", "mood", "语气", "情绪")
STYLE_COL_ALIASES = ("style", "type", "风格", "类型")
ID_COL_ALIASES = ("id", "uuid", "doc_id", "编号")


def _find_col(fieldnames: list[str], aliases: tuple[str, ...]) -> str | None:
    lower_map = {f.lower().strip(): f for f in fieldnames}
    for alias in aliases:
        if alias.lower() in lower_map:
            return lower_map[alias.lower()]
    return None


def _coerce_platform(value: str) -> str:
    """CSV 里可能写"小红书"，要转成 xiaohongshu。"""
    v = (value or "").strip().lower()
    # 中文 -> enum 的小映射
    zh_map = {
        "小红书": "xiaohongshu",
        "抖音": "douyin",
        "朋友圈": "wechat_moments",
        "微博": "weibo",
        "知乎": "zhihu",
        "b站": "bilibili", "b 站": "bilibili", "哔哩哔哩": "bilibili",
        "twitter": "twitter", "推特": "twitter",
        "instagram": "instagram", "ins": "instagram",
    }
    if v in zh_map:
        return zh_map[v]
    if v in PLATFORM_VALUES:
        return v
    return v  # 不强行改，让 schema 校验报错


def _coerce_tags(value: str) -> list[str]:
    if not value:
        return []
    for sep in ("|", ";", "、", "/"):
        if sep in value:
            return [t.strip() for t in value.split(sep) if t.strip()]
    return [value.strip()]


def _next_id(existing_ids: set[str], prefix: str = "user") -> str:
    n = 1
    while f"{prefix}_{n:04d}" in existing_ids:
        n += 1
    return f"{prefix}_{n:04d}"


def import_jsonl(
    src: Path,
    dst: Path,
    *,
    append: bool = False,
) -> tuple[int, int, list[str]]:
    """从 JSONL 导入。返回 (导入条数, 跳过条数, 错误列表)。"""
    imported, skipped, errs = 0, 0, []
    existing_ids: set[str] = set()
    if dst.exists() and append:
        for line in dst.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if "id" in rec:
                    existing_ids.add(rec["id"])
            except Exception:
                continue

    dst.parent.mkdir(parents=True, exist_ok=True)
    out_mode = "a" if append else "w"

    with src.open(encoding="utf-8") as fin, dst.open(mode=out_mode, encoding="utf-8") as fout:
        for ln, raw in enumerate(fin, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as e:
                errs.append(f"line {ln}: bad json - {e}")
                skipped += 1
                continue

            if "id" not in rec:
                rec["id"] = _next_id(existing_ids)
            existing_ids.add(rec["id"])

            ok, verrs = validate_corpus_record(rec)
            if not ok:
                errs.append(f"line {ln} id={rec.get('id')}: {verrs}")
                skipped += 1
                continue

            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            imported += 1
    return imported, skipped, errs


def import_csv(
    src: Path,
    dst: Path,
    *,
    text_col: str | None,
    platform_col: str | None,
    scene_col: str | None,
    tags_col: str | None,
    tone_col: str | None,
    style_col: str | None,
    id_col: str | None,
    append: bool = False,
) -> tuple[int, int, list[str]]:
    imported, skipped, errs = 0, 0, []
    existing_ids: set[str] = set()
    if dst.exists() and append:
        for line in dst.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if "id" in rec:
                    existing_ids.add(rec["id"])
            except Exception:
                continue

    dst.parent.mkdir(parents=True, exist_ok=True)
    out_mode = "a" if append else "w"

    with src.open(encoding="utf-8-sig", newline="") as fin, \
         dst.open(mode=out_mode, encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        cols = reader.fieldnames or []
        tcol = text_col or _find_col(cols, TEXT_COL_ALIASES)
        pcol = platform_col or _find_col(cols, PLATFORM_COL_ALIASES)
        scol = scene_col or _find_col(cols, SCENE_COL_ALIASES)
        tagcol = tags_col or _find_col(cols, TAGS_COL_ALIASES)
        tonecol = tone_col or _find_col(cols, TONE_COL_ALIASES)
        stycol = style_col or _find_col(cols, STYLE_COL_ALIASES)
        idcol = id_col or _find_col(cols, ID_COL_ALIASES)

        if not tcol:
            errs.append(f"CSV 找不到 text 列（候选：{TEXT_COL_ALIASES}）")
            return 0, 0, errs
        if not pcol:
            errs.append(f"CSV 找不到 platform 列（候选：{PLATFORM_COL_ALIASES}）")
            return 0, 0, errs

        for ln, row in enumerate(reader, start=2):
            rec: dict = {
                "id": (row.get(idcol) if idcol else "") or _next_id(existing_ids),
                "platform": _coerce_platform(row.get(pcol, "")),
                "scene": (row.get(scol, "") if scol else "") or "other",
                "text": (row.get(tcol) or "").strip(),
            }
            existing_ids.add(rec["id"])
            if tagcol and row.get(tagcol):
                rec["tags"] = _coerce_tags(row[tagcol])
            if tonecol and row.get(tonecol):
                rec["tone"] = row[tonecol].strip()
            if stycol and row.get(stycol):
                rec["style"] = row[stycol].strip()
            ok, verrs = validate_corpus_record(rec)
            if not ok:
                errs.append(f"line {ln}: {verrs}")
                skipped += 1
                continue
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            imported += 1
    return imported, skipped, errs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="导入文案到 copygen skill 的文案库")
    p.add_argument("--from", dest="src", help="源文件路径（JSONL 或 CSV）")
    p.add_argument("--target", dest="dst", default=str(DEFAULT_TARGET),
                   help=f"目标 JSONL（默认 {DEFAULT_TARGET}）")
    p.add_argument("--append", action="store_true", help="追加而非覆盖")
    # CSV 列名
    p.add_argument("--text-col", default=None)
    p.add_argument("--platform-col", default=None)
    p.add_argument("--scene-col", default=None)
    p.add_argument("--tags-col", default=None)
    p.add_argument("--tone-col", default=None)
    p.add_argument("--style-col", default=None)
    p.add_argument("--id-col", default=None)
    p.add_argument("--info", action="store_true", help="打印目标文件信息后退出")
    args = p.parse_args(argv)

    src = Path(args.src) if args.src else None
    dst = Path(args.dst)

    if args.info:
        if dst.exists():
            lines = [l for l in dst.read_text(encoding="utf-8").splitlines() if l.strip()]
            print(f"{dst}: {len(lines)} 条")
            plats: dict[str, int] = {}
            for ln in lines:
                try:
                    rec = json.loads(ln)
                    p_id = rec.get("platform", "unknown")
                    plats[p_id] = plats.get(p_id, 0) + 1
                except Exception:
                    pass
            for k, v in sorted(plats.items(), key=lambda x: -x[1]):
                print(f"  - {k}: {v}")
        else:
            print(f"{dst}: 文件不存在")
        return 0

    if src is None:
        p.error("--from 必填（或用 --info）")

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 2

    if src.suffix.lower() == ".csv":
        imp, skp, errs = import_csv(
            src, dst,
            text_col=args.text_col, platform_col=args.platform_col,
            scene_col=args.scene_col, tags_col=args.tags_col,
            tone_col=args.tone_col, style_col=args.style_col,
            id_col=args.id_col, append=args.append,
        )
    else:
        imp, skp, errs = import_jsonl(src, dst, append=args.append)

    print(f"导入 {imp} 条，跳过 {skp} 条，错误 {len(errs)} 条 -> {dst}")
    for e in errs[:20]:
        print("  !", e)
    if len(errs) > 20:
        print(f"  ... 还有 {len(errs) - 20} 条错误省略")
    return 0 if imp > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())