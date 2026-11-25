#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 data/resources.yml 里所有资源链接是否还活着。

用法：
    python scripts/check_links.py
    python scripts/check_links.py --timeout 20 --retry 2
    python scripts/check_links.py --proxy http://127.0.0.1:7890
    python scripts/check_links.py --json out.json

依赖：只用标准库，不装第三方包。

状态分四种：
    OK          能访问，或者有访问限制但站点存在
    TIMEOUT     超时，多半是网络问题，不代表链接失效
    UNREACHABLE 连不上（DNS、拒绝连接），同上
    DEAD        404 或 410，这才是真的失效

退出码：
    0  没有确认失效的链接
    1  有确认失效的链接（DEAD）
    2  文件读不到或格式不对

为什么要把超时单独列出来：这个脚本主要在国内网络环境跑，
访问国外的站点（Google Scholar、PubMed、MDN）超时是正常的，
把它们算成失效会产生大量误报，项目就不可信了。
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YML = ROOT / "data" / "resources.yml"
UA = "Mozilla/5.0 (compatible; modern-knowledge-map link checker)"


def parse_resources(path: Path):
    """解析 resources.yml 的最小子集，不依赖 pyyaml。"""
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


def check_once(url: str, timeout: int, proxy: str | None):
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    else:
        opener = urllib.request.build_opener()

    req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA})
    try:
        with opener.open(req, timeout=timeout) as resp:
            code = resp.getcode()
            if 200 <= code < 400:
                return "OK", f"HTTP {code}"
            return "UNREACHABLE", f"HTTP {code}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return "OK", f"HTTP {e.code}（有访问限制）"
        if e.code in (404, 410):
            return "DEAD", f"HTTP {e.code}"
        return "UNREACHABLE", f"HTTP {e.code}"
    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "timed out" in reason.lower() or "timeout" in reason.lower():
            return "TIMEOUT", "请求超时"
        return "UNREACHABLE", f"连接失败：{reason[:40]}"
    except TimeoutError:
        return "TIMEOUT", "请求超时"
    except Exception as e:
        return "UNREACHABLE", f"{type(e).__name__}: {str(e)[:40]}"


def check(url: str, timeout: int, retry: int, proxy: str | None):
    last = ("UNREACHABLE", "未执行")
    for attempt in range(retry + 1):
        status, note = check_once(url, timeout, proxy)
        last = (status, note)
        if status == "OK":
            return last
        if attempt < retry:
            time.sleep(1.5)
    return last


def main():
    ap = argparse.ArgumentParser(description="检查资源链接")
    ap.add_argument("--timeout", type=int, default=12, help="单个请求超时秒数")
    ap.add_argument("--retry", type=int, default=1, help="失败后重试次数")
    ap.add_argument("--proxy", help="代理地址，例如 http://127.0.0.1:7890")
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
    counts = {"OK": 0, "TIMEOUT": 0, "UNREACHABLE": 0, "DEAD": 0}
    no_verified = 0

    for e in entries:
        name = e.get("name", "(无名)")
        url = e["url"]
        status, note = check(url, args.timeout, args.retry, args.proxy)
        counts[status] = counts.get(status, 0) + 1
        if not e.get("verified"):
            no_verified += 1
        tag = {"OK": "OK  ", "DEAD": "DEAD", "TIMEOUT": "TIME", "UNREACHABLE": "FAIL"}[status]
        print(f"[{tag}] {name:<30} {note:<22} {url}")
        results.append({
            "name": name, "url": url,
            "level": e.get("level", ""), "verified": e.get("verified", ""),
            "status": status, "note": note,
        })

    print()
    print(f"共 {len(entries)} 条：OK {counts['OK']}，"
          f"超时 {counts['TIMEOUT']}，不可达 {counts['UNREACHABLE']}，确认失效 {counts['DEAD']}")
    if counts["TIMEOUT"] or counts["UNREACHABLE"]:
        print("提示：超时和不可达多半是网络问题，换个网络或用 --proxy 再跑一次再下结论。")
    if no_verified:
        print(f"提醒：有 {no_verified} 条缺少 verified 字段，请补核验日期")

    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"结果已写入 {args.json}")

    return 1 if counts["DEAD"] else 0


if __name__ == "__main__":
    sys.exit(main())