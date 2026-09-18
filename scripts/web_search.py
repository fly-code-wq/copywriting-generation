"""可选的联网检索 — 当本地文案库不够时使用。

支持两种 provider：
    tavily    — 推荐，需要 `pip install tavily-python`
    webfetch  — 直接用 requests（标准库无 requests，需 pip install requests；或退化为 urllib）

用法：
    python scripts/web_search.py --query "小红书 文案 治愈 旅行" --provider tavily --top 5 --json
    python scripts/web_search.py --query "朋友圈文案 高级感" --provider webfetch --top 3

未安装对应包时自动 fallback 到 urllib。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _try_tavily(query: str, top_k: int) -> list[dict] | None:
    try:
        from tavily import TavilyClient  # type: ignore
    except ImportError:
        return None
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return None
    try:
        client = TavilyClient(api_key=api_key)
        r = client.search(query=query, max_results=top_k, include_raw_content=False)
        return [
            {"url": x.get("url", ""), "title": x.get("title", ""), "snippet": x.get("content", "")[:300]}
            for x in r.get("results", [])
        ]
    except Exception as e:
        print(f"[WARN] tavily 调用失败: {e}", file=sys.stderr)
        return None


def _urllib_fetch(query: str, top_k: int) -> list[dict]:
    """最简的 DuckDuckGo HTML 抓取。仅作为完全离线的兜底，结果质量有限。"""
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "copygen-skill/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[WARN] 联网失败: {e}", file=sys.stderr)
        return []
    # 简陋正则抽 title + snippet
    import re
    out: list[dict] = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]*>(.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                         html, flags=re.DOTALL):
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        snippet = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        out.append({"url": "", "title": title, "snippet": snippet})
        if len(out) >= top_k:
            break
    return out


def search_web(query: str, *, top_k: int = 5, provider: str = "auto") -> list[dict]:
    if provider in ("tavily", "auto"):
        r = _try_tavily(query, top_k)
        if r is not None:
            return r
        if provider == "tavily":
            print("[ERR] tavily 未安装或无 API key", file=sys.stderr)
            return []
    # fallback
    return _urllib_fetch(query, top_k)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="联网检索类似文案")
    p.add_argument("--query", required=True)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--provider", choices=["auto", "tavily", "webfetch"], default="auto")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    results = search_web(args.query, top_k=args.top, provider=args.provider)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    if not results:
        print("[WARN] 无结果或联网失败。请检查 TAVILY_API_KEY 或网络。")
        return 1

    print(f"=== 联网检索结果 ({len(results)}) ===")
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r.get('title','')}")
        if r.get("url"):
            print(f"    {r['url']}")
        print(f"    {r.get('snippet','')[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())