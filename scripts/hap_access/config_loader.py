"""config_loader: 从统一配置文件 hap-config.json 加载凭据与应用列表。

加载顺序（优先级高→低）：
  1. config/hap-config.local.json（本地覆盖，不入 git）
  2. config/hap-config.json（模板，随仓库分发）

Token 自动刷新：
  当 personal_mcp.token.current_token 为空或已过期时，自动用
  account + password 调 md-generate-mcp-config 刷新，并回写 local 配置。

对外接口：
  load_config()           → dict  完整配置
  resolve_app(app_name)   → dict  构建可供 MCPClient 使用的虚拟 profile（含自动刷新）
  save_config(cfg)        → None  写回配置（agent 运行时维护 token/apps）
  ensure_token()          → str   确保 token 有效并返回
  list_apps()             → list  列出所有已注册应用
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# Token 寿命约 24h；留 1h buffer 提前判过期
TOKEN_TTL_HOURS = 23

# ClawCRM SaaS 官方个人 MCP 集成应用 id
DEFAULT_OAUTH_APP_ID = "69bcae07257900ec41aa2733"

# md-generate-mcp-config 可执行路径
MD_GEN_BIN = Path.home() / ".qoder" / "skills" / "hap-oauth-mcp" / ".venv" / "bin" / "md-generate-mcp-config"
MCP_KEY = "HAP Personal MCP"


class TokenRefreshError(RuntimeError):
    """Token 刷新失败。"""


def _config_dir() -> Path:
    """配置目录：skill 仓库根下的 config/"""
    override = os.environ.get("HAP_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    # scripts/hap_access/config_loader.py → ../../config
    return Path(__file__).resolve().parent.parent.parent / "config"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_account(raw: str) -> str:
    s = raw.strip()
    if s.startswith("+"):
        return s
    if len(s) == 11 and s.isdigit() and s.startswith("1"):
        return "+86" + s
    return s


def load_config() -> dict[str, Any]:
    """加载配置，local 优先。"""
    d = _config_dir()
    local = d / "hap-config.local.json"
    default = d / "hap-config.json"
    path = local if local.exists() else default
    if not path.exists():
        raise FileNotFoundError(
            f"统一配置文件不存在：{default}\n"
            f"  下一步：从 hap-config.json 模板复制并填入凭据"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(cfg: dict[str, Any]) -> Path:
    """写回配置到 local 文件（避免污染模板）。"""
    d = _config_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "hap-config.local.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _is_token_expired(token_block: dict) -> bool:
    """判断 token 是否过期。"""
    exp_str = token_block.get("expires_at", "")
    if not exp_str:
        return True
    try:
        exp = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
    except ValueError:
        return True
    return _now() >= exp


def _refresh_token(cfg: dict) -> str:
    """用 account+password 调 md-generate-mcp-config 刷新 token，更新 cfg 并回写。

    返回新的 token 字符串。
    """
    token_block = cfg.get("personal_mcp", {}).get("token", {})
    account = token_block.get("account", "") or os.environ.get("MINGDAO_ACCOUNT", "")
    password = token_block.get("password", "") or os.environ.get("MINGDAO_PASSWORD", "")

    if not account or not password:
        raise TokenRefreshError(
            "token 已过期且无法自动刷新：account/password 未配置。\n"
            "  请在 hap-config.local.json 的 personal_mcp.token 中填写，"
            "或 export MINGDAO_ACCOUNT/MINGDAO_PASSWORD。"
        )

    account = _normalize_account(account)
    oauth_app_id = os.environ.get("MINGDAO_OAUTH_APP_ID", DEFAULT_OAUTH_APP_ID).strip()

    # 找 md-generate-mcp-config
    bin_path = MD_GEN_BIN
    if not bin_path.exists():
        # 回退：尝试 PATH
        import shutil
        on_path = shutil.which("md-generate-mcp-config")
        if on_path:
            bin_path = Path(on_path)
        else:
            raise TokenRefreshError(
                f"md-generate-mcp-config 不存在: {MD_GEN_BIN}\n"
                "  请先安装 hap-oauth-mcp skill。"
            )

    cmd = [
        str(bin_path),
        "--account", account,
        "--password", password,
        "--oauth-app-id", oauth_app_id,
        "--no-open-browser",
        "--skip-wait",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as e:
        raise TokenRefreshError("md-generate-mcp-config 超时（60s）") from e
    except OSError as e:
        raise TokenRefreshError(f"md-generate-mcp-config 启动失败: {e}") from e

    if proc.returncode != 0:
        err_tail = (proc.stderr or "")[-400:].strip()
        raise TokenRefreshError(
            f"md-generate-mcp-config exit={proc.returncode}; stderr: {err_tail}"
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise TokenRefreshError(f"md-generate-mcp-config 输出非 JSON: {e}") from e

    entry = data.get(MCP_KEY) or next(iter(data.values()), {}) if isinstance(data, dict) else {}
    url = (entry or {}).get("url") if isinstance(entry, dict) else None
    if not url or "Authorization=Bearer" not in url:
        raise TokenRefreshError("md-generate-mcp-config 输出里没找到合法的 MCP URL")

    # 从 URL 提取 token
    # URL 格式: https://api2.mingdao.com/mcp?Authorization=Bearer%20<TOKEN>
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    auth_val = params.get("Authorization", [""])[0]
    token = auth_val.replace("Bearer ", "").strip()
    if not token:
        # fallback: 直接从 URL 截取
        marker = "Bearer%20"
        idx = url.find(marker)
        if idx >= 0:
            token = urllib.parse.unquote(url[idx + len(marker):])
        else:
            raise TokenRefreshError("无法从刷新结果 URL 中提取 token")

    # 更新 cfg
    now = _now()
    expires = now + timedelta(hours=TOKEN_TTL_HOURS)
    cfg.setdefault("personal_mcp", {}).setdefault("token", {})
    cfg["personal_mcp"]["token"]["current_token"] = token
    cfg["personal_mcp"]["token"]["expires_at"] = expires.isoformat(timespec="seconds").replace("+00:00", "Z")

    # 回写
    save_config(cfg)
    print(f"[config_loader] token 已刷新，有效期至 {cfg['personal_mcp']['token']['expires_at']}", file=sys.stderr)
    return token


def ensure_token(cfg: dict | None = None) -> str:
    """确保 personal_mcp token 有效：未过期直接返回，过期则自动刷新。"""
    if cfg is None:
        cfg = load_config()
    token_block = cfg.get("personal_mcp", {}).get("token", {})
    current = token_block.get("current_token", "")

    if current and not _is_token_expired(token_block):
        return current

    # 需要刷新
    return _refresh_token(cfg)


def resolve_app(app_name: str, prefer_mode: str | None = None) -> dict[str, Any]:
    """根据应用名称从配置中构建虚拟 profile（供 MCPClient 使用）。

    查找策略：
      1. 若 prefer_mode 指定，只在该 section 查找
      2. 否则先找 app_mcp（凭据独立），再找 personal_mcp

    personal_mcp 模式下会自动确保 token 有效。
    """
    cfg = load_config()
    sections = (
        [prefer_mode] if prefer_mode
        else ["app_mcp", "personal_mcp"]
    )
    for section in sections:
        block = cfg.get(section)
        if not block:
            continue
        for app in block.get("apps", []):
            if app.get("app_name") == app_name:
                return _build_profile(section, block, app, cfg)
    available = []
    for section in ("personal_mcp", "app_mcp"):
        for app in cfg.get(section, {}).get("apps", []):
            available.append(f"  - [{section}] {app.get('app_name')}")
    raise LookupError(
        f"配置中未找到应用 '{app_name}'。可用应用：\n" + "\n".join(available)
    )


def list_apps() -> list[dict[str, Any]]:
    """列出配置中所有应用（含 mode 信息）。"""
    cfg = load_config()
    result = []
    for section in ("personal_mcp", "app_mcp"):
        block = cfg.get(section, {})
        for app in block.get("apps", []):
            result.append({**app, "mode": section})
    return result


def get_token(cfg: dict | None = None) -> str:
    """获取 personal_mcp 的 current_token（不刷新，仅读取）。"""
    if cfg is None:
        cfg = load_config()
    return cfg.get("personal_mcp", {}).get("token", {}).get("current_token", "")


def _build_profile(section: str, block: dict, app: dict, cfg: dict) -> dict[str, Any]:
    """将配置片段转为 MCPClient 兼容的 profile dict。"""
    api_base = block.get("api_base", "https://api.mingdao.com")
    if section == "app_mcp":
        return {
            "mode": "app_mcp",
            "api_base": api_base,
            "appkey": app.get("appkey", ""),
            "sign": app.get("sign", ""),
        }
    # personal_mcp — 确保 token 有效
    token = ensure_token(cfg)
    return {
        "mode": "personal_mcp",
        "api_base": api_base,
        "app_id": app.get("app_id", ""),
        "ai_description": app.get("ai_description", ""),
        "token_source": f"url:{api_base}/mcp?access_token={token}" if token else "",
    }
