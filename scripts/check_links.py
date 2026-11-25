#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 data/resources.yml 里所有资源链接是否还活着。

用法：
    python scripts/check_links.py
    python scripts/check_links.py --timeout 15
    python scripts/check_links.py --json out.json

依赖：只用标准库，不装第三方包。

退出码：
    0  全部可访问
    1  有失效链接
    2  文件读不到或格式不对
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YML = ROOT / "data" / "resources.yml"
UA = "Mozilla/5.0 (compatible; modern-knowledge-map link checker)"


def parse_resources(path: Path):
    """解析 resources.yml 的最小子集，不依赖 pyyaml。

    只认这种结构：
      - name: xxx
        url: https://...
        desc: xxx
        level: A
        verified: 2026-11
        topic: xxx
    """
    entries = []
    cur = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s*-\s*name:\s*(.+)$", line)
        if m:
            if cur.get("url"):
                entries.append(cur)
            cur = {"name": m.group(1).strip()}
            continue
        m = re.match(r"^\s+(name|url|desc|level|verified|topic):\s*(.+)$", line)
        if m and cur is not None:
            cur[m.group(1)] = m.group(2).strip()
    if cur.get("url"):
        entries.append(cur)
    return entries


def check(url: str, timeout: int):
    """返回 (状态, 说明)。状态为 ok / notfound / error。"""
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if 200 <= code < 400:
                return "ok", f"HTTP {code}"
            return "error", f"HTTP {code}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            # 有访问控制但站点存在，算活着
            return "ok", f"HTTP {e.code}（有访问限制）"
        if e.code == 404:
            return "notfound", "HTTP 404"
        return "error", f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return "error", f"连接失败：{e.reason}"
    except Exception as e:
        return "error", f"异常：{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description="检查资源链接")
    ap.add_argument("--timeout", type=int, default=12, help="单个请求超时秒数")
    ap.add_argument("--json", metavar="PATH", help="把结果写到 JSON 文件")
    args = ap.parse_args()

    if not YML.exists():
        print(f"找不到 {YML}", file=sys.stderr)
        return 2

    entries = parse_resources(YML)
    if not entries:
        print("没有解析到任何资源，检查文件格式", file=sys.stderr)
        return 2

    results = []
    bad = 0
    no_verified = 0

    for e in entries:
        name = e.get("name", "(无名)")
        url = e["url"]
        status, note = check(url, args.timeout)
        if not e.get("verified"):
            no_verified += 1
        mark = "OK  " if status == "ok" else "FAIL"
        if status != "ok":
            bad += 1
        print(f"[{mark}] {name:<28} {note:<24} {url}")
        results.append({
            "name": name,
            "url": url,
            "level": e.get("level", ""),
            "verified": e.get("verified", ""),
            "status": status,
            "note": note,
        })

    print()
    print(f"共 {len(entries)} 条，可访问 {len(entries) - bad} 条，失效 {bad} 条")
    if no_verified:
        print(f"提醒：有 {no_verified} 条缺少 verified 字段，请补核验日期")

    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"结果已写入 {args.json}")

    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())