#!/usr/bin/env python3
"""
明道云 Personal MCP Token 透明管理：缓存 + 自动刷新。

设计目标
--------
让所有下游脚本（review_project.py 等）调用一行 `get_mcp_url()`
就拿到一个**保证有效**的 MCP URL，无需关心 token 怎么来、何时过期。

凭证来源（一次性配置，不进对话）
--------------------------------
shell profile (~/.zshrc / ~/.bashrc) 里 export 一次：

    export MINGDAO_ACCOUNT='+8615801477125'        # E.164 必填
    export MINGDAO_PASSWORD='your_password'
    # export MINGDAO_OAUTH_APP_ID='...'            # 可选；默认 ClawCRM SaaS 官方

如果 MINGDAO_ACCOUNT 是 11 位纯数字以 1 开头，会自动补 '+86'。

缓存
----
~/.cache/hap-mcp/token.json
{
  "url": "https://api2.mingdao.com/mcp?Authorization=Bearer%20<TOK>",
  "fetched_at": "2026-05-01T10:00:00Z",
  "expires_at": "2026-05-02T09:00:00Z"   # fetched + 23h，留 1h buffer
}

CLI
---
    python3 mcp_token.py            # 打印当前有效 URL（必要时自动刷新）
    python3 mcp_token.py --refresh  # 强制刷新
    python3 mcp_token.py --status   # 打印缓存状态（不暴露 token）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---- 常量 -----------------------------------------------------------------

# token 实际寿命约 24h；留 1h 安全 buffer，提前判过期
TOKEN_TTL_HOURS = 23

# ClawCRM SaaS 官方个人 MCP 集成应用 id（hap-oauth-mcp 的 docs/reference.md 锚点）
DEFAULT_OAUTH_APP_ID = "69bcae07257900ec41aa2733"

# md-generate-mcp-config 可执行路径（hap-oauth-mcp skill 的 venv 入口）
MD_GEN_BIN = Path.home() / ".qoder" / "skills" / "hap-oauth-mcp" / ".venv" / "bin" / "md-generate-mcp-config"

# 输出 JSON 顶层 key（脚本默认）
MCP_KEY = "HAP Personal MCP"


def _resolve_cache_dir() -> Path:
    """缓存路径解析：env `HAP_MCP_CACHE_DIR` 覆盖 > ~/.cache/hap-mcp > /tmp/hap-mcp 回退。

    某些 sandbox（如 Qoder 内置 shell）限制写 ~/.cache；遇到 PermissionError 时自动回退到 /tmp。
    """
    override = os.environ.get("HAP_MCP_CACHE_DIR", "").strip()
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    candidates.append(Path.home() / ".cache" / "hap-mcp")
    candidates.append(Path("/tmp/hap-mcp"))
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_test"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
            return d
        except (OSError, PermissionError):
            continue
    return candidates[-1]


CACHE_DIR = _resolve_cache_dir()
CACHE_FILE = CACHE_DIR / "token.json"


# ---- 工具函数 -------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_account(raw: str) -> str:
    """11 位以 1 开头的大陆号自动补 +86。其它原样返回。"""
    s = raw.strip()
    if s.startswith("+"):
        return s
    if len(s) == 11 and s.isdigit() and s.startswith("1"):
        return "+86" + s
    return s


def _read_cache() -> dict | None:
    if not CACHE_FILE.exists():
        return None
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(url: str) -> dict:
    fetched = _now()
    expires = fetched + timedelta(hours=TOKEN_TTL_HOURS)
    payload = {
        "url": url,
        "fetched_at": fetched.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires_at": expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CACHE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except PermissionError as e:
        raise MCPCredentialError(f"缓存写入失败 ({CACHE_FILE}): {e}") from e
    try:
        os.chmod(CACHE_FILE, 0o600)
    except OSError:
        pass
    return payload


def _is_expired(cache: dict) -> bool:
    exp_str = cache.get("expires_at")
    if not exp_str:
        return True
    try:
        exp = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
    except ValueError:
        return True
    return _now() >= exp


def _encode_bearer_space(url: str) -> str:
    """Personal MCP URL 里 'Bearer <tok>' 的空格必须 URL-encode 成 %20，否则 urllib 拒绝。"""
    return url.replace("Bearer ", "Bearer%20")


# ---- 刷新 -----------------------------------------------------------------

class MCPCredentialError(RuntimeError):
    """凭证缺失或刷新失败。错误消息已脱敏（不含密码/token）。"""


def _refresh_from_md_generate() -> str:
    """调 md-generate-mcp-config 拿一个新 URL。失败抛 MCPCredentialError。"""
    raw_account = os.environ.get("MINGDAO_ACCOUNT", "").strip()
    password = os.environ.get("MINGDAO_PASSWORD", "").strip()
    oauth_app_id = os.environ.get("MINGDAO_OAUTH_APP_ID", DEFAULT_OAUTH_APP_ID).strip()

    if not raw_account or not password:
        raise MCPCredentialError(
            "MINGDAO_ACCOUNT / MINGDAO_PASSWORD 未设置。"
            "请在 shell profile 里 export 一次（不要写进对话/代码）。"
        )

    if not MD_GEN_BIN.exists():
        raise MCPCredentialError(
            f"md-generate-mcp-config 不存在: {MD_GEN_BIN}。"
            "请先安装 hap-oauth-mcp skill 并完成 install.sh。"
        )

    account = _normalize_account(raw_account)

    cmd = [
        str(MD_GEN_BIN),
        "--account", account,
        "--password", password,
        "--oauth-app-id", oauth_app_id,
        "--no-open-browser",
        "--skip-wait",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as e:
        raise MCPCredentialError("md-generate-mcp-config 超时（60s）") from e
    except OSError as e:
        raise MCPCredentialError(f"md-generate-mcp-config 启动失败: {e}") from e

    if proc.returncode != 0:
        # stderr 可能含敏感信息，截断；不含 stdout
        err_tail = (proc.stderr or "")[-400:].strip()
        raise MCPCredentialError(
            f"md-generate-mcp-config exit={proc.returncode}; stderr_tail: {err_tail}"
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise MCPCredentialError(f"md-generate-mcp-config 输出非 JSON: {e}") from e

    entry = data.get(MCP_KEY) or next(iter(data.values()), {}) if isinstance(data, dict) else {}
    url = (entry or {}).get("url") if isinstance(entry, dict) else None
    if not url or "Authorization=Bearer" not in url:
        raise MCPCredentialError("md-generate-mcp-config 输出里没找到合法的 MCP URL")

    return _encode_bearer_space(url)


# ---- 对外 API -------------------------------------------------------------

def get_mcp_url(force_refresh: bool = False) -> str:
    """
    返回当前有效的 Personal MCP URL（已 URL-encode 空格）。

    流程：
      1. force_refresh=True：直接刷新
      2. 缓存存在且未过期：返回缓存
      3. 否则：刷新并写缓存

    凭证缺失或刷新失败时抛 MCPCredentialError，调用方按需 try/except。
    """
    if not force_refresh:
        cache = _read_cache()
        if cache and not _is_expired(cache):
            url = cache.get("url")
            if url:
                return _encode_bearer_space(url)

    url = _refresh_from_md_generate()
    _write_cache(url)
    return url


# ---- CLI ------------------------------------------------------------------

def _redact_url(url: str) -> str:
    """打印用：保留协议+域名，token 只露最后 6 位。"""
    if "Bearer" not in url:
        return url[:40] + "..."
    head, _, tail = url.partition("Bearer")
    tail = tail.lstrip("%20").lstrip(" ")
    return f"{head}Bearer%20...{tail[-6:]}"


def _cmd_status() -> int:
    cache = _read_cache()
    if not cache:
        print("cache: <empty>")
        return 0
    expired = _is_expired(cache)
    print(f"cache_file:  {CACHE_FILE}")
    print(f"fetched_at:  {cache.get('fetched_at')}")
    print(f"expires_at:  {cache.get('expires_at')}")
    print(f"expired:     {expired}")
    print(f"url_redact:  {_redact_url(cache.get('url', ''))}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refresh", action="store_true", help="强制刷新（忽略缓存）")
    p.add_argument("--status", action="store_true", help="打印缓存状态（脱敏，不暴露 token）")
    args = p.parse_args()

    if args.status:
        return _cmd_status()

    try:
        url = get_mcp_url(force_refresh=args.refresh)
    except MCPCredentialError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
