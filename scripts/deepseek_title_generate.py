#!/usr/bin/env python3
"""Generate Hong Kong Regal hotel Xiaohongshu titles with DeepSeek."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


SYSTEM_PROMPT = """你是香港富豪酒店小红书标题优化专家。
任务：根据用户提供的正文或 brief，生成高信息密度的小红书标题。
硬规则：
1. 每个标题不超过20个字符。
2. 每个标题必须包含且只包含一次“香港”。
3. 不使用emoji。
4. 每个标题优先16-20字符，尽量18-20字符。
5. 每个标题优先使用1-2个结构标点：丨、+、，、！。
6. 优先带酒店名、地标、行程天数、约几分钟交通时间、接驳/步行等量化信息。
7. 必须把买点连接到情绪收益，如省心、少折腾、不赶路、更顺、不怕雨、不狼狈。
8. 不编造正文没有的酒店名、地标、距离、价格、权益、活动或承诺。
9. 不使用“必住”“全网最低”“最划算”“闭眼冲”等夸大表达。
10. 只要写通勤、交通、接驳、步行、车程时间，必须加“约”，例如“约15分钟”“步行约2分钟”；禁止写“15分钟”“2分钟”“15分”。
11. 不要为了压缩标题删掉“约”，也不要把“约15分钟”压缩成“15分”；宁可删掉弱修饰词。
输出格式：
只输出编号标题列表，每行格式为：1. 标题（N字符）- 类型：...
"""


def read_prompt(positional_prompt: str | None) -> str:
    if positional_prompt:
        return positional_prompt
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return data
    raise SystemExit("ERROR: provide note text as an argument or pipe it through stdin.")


def build_user_prompt(note: str, count: int) -> str:
    return f"""请基于以下正文或brief，生成{count}个标题。

正文或brief：
{note}

额外要求：
- 尽量选用正文里的酒店名、地标和交通信息。
- 如果正文没有行程天数，可以使用2天1夜、3天2晚、5天4晚、7天6晚等旅游标题语感，但不要虚构价格、距离或权益。
- 输出前请自行检查字符数，标点也算1个字符。
- 每条标题必须包含且只包含一次“香港”；不符合就重写，不要输出。
- 交通时间、接驳时间、步行时间必须使用“约X分钟”表达；没有“约”的时间标题不要输出。
- 不要为了凑20字符删除“约”或“分钟”。
"""


def post_json(url: str, api_key: str, payload: dict, timeout: int) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"REQUEST FAILED: {exc}") from exc


def find_deepseek_use_script() -> Path | None:
    home = Path.home()
    candidates = [
        home / ".agents" / "skills" / "deepseek-use" / "scripts" / "deepseek_use.py",
        home / ".codex" / "skills" / "deepseek-use" / "scripts" / "deepseek_use.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def call_global_deepseek_use(args: argparse.Namespace, note: str) -> int:
    script = find_deepseek_use_script()
    if not script:
        raise SystemExit(
            f"ERROR: set {args.api_key_env}, or install the global deepseek-use skill before calling DeepSeek."
        )

    prompt = build_user_prompt(note, args.count)
    cmd = [
        sys.executable,
        str(script),
        "--system",
        SYSTEM_PROMPT,
        "--model",
        args.model,
        "--max-tokens",
        "1200",
    ]
    if args.raw:
        cmd.append("--raw")
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=args.timeout + 10,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"ERROR: DeepSeek global skill timed out after {args.timeout + 10}s.") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"ERROR: DeepSeek global skill failed: {detail}")

    print(result.stdout.rstrip())
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate XHS titles for Regal Hong Kong hotel notes with DeepSeek.")
    parser.add_argument("prompt", nargs="?", help="Note body or brief. If omitted, stdin is used.")
    parser.add_argument("--count", type=int, default=10, help="Number of titles to generate. Default: 10")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model name. Default: {DEFAULT_MODEL}")
    parser.add_argument("--base-url", default=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY", help="Environment variable holding the API key.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--raw", action="store_true", help="Print raw JSON response.")
    parser.add_argument("--dry-run", action="store_true", help="Print request payload without calling the API.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    note = read_prompt(args.prompt)
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(note, args.count)},
        ],
        "stream": False,
        "thinking": {"type": "disabled"},
    }
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        return call_global_deepseek_use(args, note)

    endpoint = args.base_url.rstrip("/") + "/chat/completions"
    response = post_json(endpoint, api_key, payload, args.timeout)
    if args.raw:
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0

    try:
        content = response["choices"][0]["message"].get("content", "")
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"ERROR: unexpected response shape: {json.dumps(response, ensure_ascii=False)}") from exc
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
