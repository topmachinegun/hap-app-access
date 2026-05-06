"""Profile: hap-access 的单一事实源凭据存储。

存储位置（覆盖顺序）：
  1. $HAP_PROFILE_DIR/<name>.json
  2. ~/.local/share/hap-app-access/profiles/<name>.json

Schema（JSON 字段）：
  name            : profile 名称，建议英文
  mode            : personal_mcp | app_mcp | v3_api
  api_base        : https://api.mingdao.com（默认）；私有化部署带 /api 后缀
  mcp_url         : personal_mcp / app_mcp 必填；完整 URL 含鉴权参数
  app_id          : personal_mcp 必填；MCP 业务工具的 appId 参数
  ai_description  : personal_mcp 必填；MCP 业务工具的 ai_description 参数
  appkey          : app_mcp / v3_api 必填
  sign            : app_mcp / v3_api 必填
  token_source    : personal_mcp 可选；值形如 "broker:<broker_profile_key>"，
                    加载时调 hap-token-broker 取最新 token 拼 URL

安全约定：
  - profile 文件权限必须 0600；不满足时拒绝加载
  - profile 目录不应入版本控制；.gitignore 已默认屏蔽
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

DEFAULT_PROFILE_DIR = Path.home() / ".local" / "share" / "hap-app-access" / "profiles"
VALID_MODES = {"personal_mcp", "app_mcp", "v3_api"}


class ProfileError(RuntimeError):
    pass


def profile_dir() -> Path:
    override = os.environ.get("HAP_PROFILE_DIR")
    return Path(override).expanduser() if override else DEFAULT_PROFILE_DIR


def profile_path(name: str) -> Path:
    return profile_dir() / f"{name}.json"


def list_profiles() -> list[str]:
    d = profile_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def load(name: str) -> dict[str, Any]:
    """加载并校验 profile；不展开 token_source，由 mcp_client 加载时再解析。"""
    path = profile_path(name)
    if not path.exists():
        raise ProfileError(
            f"profile '{name}' 不存在：{path}\n"
            f"  下一步：hap-access profile --init  创建一个；或手工编辑 {path}"
        )
    _check_permission(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ProfileError(f"profile '{name}' 不是合法 JSON：{e}") from e
    _validate_schema(data, name)
    return data


def save(name: str, data: dict[str, Any]) -> Path:
    """写入 profile 并强制 0600 权限。"""
    _validate_schema(data, name)
    d = profile_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = profile_path(name)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path


def redact(data: dict[str, Any]) -> dict[str, Any]:
    """脱敏副本：用于 --show 输出。"""
    out = dict(data)
    for k in ("appkey", "sign", "mcp_url"):
        v = out.get(k)
        if isinstance(v, str) and v:
            out[k] = _mask(v)
    return out


def _mask(s: str) -> str:
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}***{s[-4:]}"


def _check_permission(path: Path) -> None:
    st = path.stat()
    mode = stat.S_IMODE(st.st_mode)
    if mode & 0o077:
        raise ProfileError(
            f"profile '{path.name}' 权限过宽（{oct(mode)}），拒绝加载。\n"
            f"  修复：chmod 600 {path}"
        )


def _validate_schema(data: dict[str, Any], name: str) -> None:
    if not isinstance(data, dict):
        raise ProfileError(f"profile '{name}' 根节点必须是对象")
    mode = data.get("mode")
    if mode not in VALID_MODES:
        raise ProfileError(
            f"profile '{name}' mode='{mode}' 非法；必须是 {sorted(VALID_MODES)} 之一"
        )
    required: dict[str, list[str]] = {
        "personal_mcp": ["app_id", "ai_description"],
        "app_mcp": ["appkey", "sign"],
        "v3_api": ["appkey", "sign"],
    }
    if mode == "personal_mcp":
        if not (data.get("mcp_url") or data.get("token_source")):
            raise ProfileError(
                f"profile '{name}' personal_mcp 必须提供 mcp_url 或 token_source"
            )
    for key in required[mode]:
        if not data.get(key):
            raise ProfileError(f"profile '{name}' mode={mode} 缺字段 '{key}'")
