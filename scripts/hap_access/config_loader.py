"""config_loader: 从统一配置文件 hap-config.json 加载凭据与应用列表。

加载顺序（优先级高→低）：
  1. config/hap-config.local.json（本地覆盖，不入 git）
  2. config/hap-config.json（模板，随仓库分发）

对外接口：
  load_config()           → dict  完整配置
  resolve_app(app_name)   → dict  构建可供 MCPClient 使用的虚拟 profile
  save_config(cfg)        → None  写回配置（agent 运行时维护 token/apps）
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    """配置目录：skill 仓库根下的 config/"""
    # 优先使用环境变量，否则回退到脚本相对路径
    override = os.environ.get("HAP_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    # scripts/hap_access/config_loader.py → ../../config
    return Path(__file__).resolve().parent.parent.parent / "config"


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
    return path


def resolve_app(app_name: str, prefer_mode: str | None = None) -> dict[str, Any]:
    """根据应用名称从配置中构建虚拟 profile（供 MCPClient 使用）。

    查找策略：
      1. 若 prefer_mode 指定，只在该 section 查找
      2. 否则先找 app_mcp（凭据独立），再找 personal_mcp
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
                return _build_profile(section, block, app)
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
    """获取 personal_mcp 的 current_token。"""
    if cfg is None:
        cfg = load_config()
    return cfg.get("personal_mcp", {}).get("token", {}).get("current_token", "")


def _build_profile(section: str, block: dict, app: dict) -> dict[str, Any]:
    """将配置片段转为 MCPClient 兼容的 profile dict。"""
    api_base = block.get("api_base", "https://api.mingdao.com")
    if section == "app_mcp":
        return {
            "mode": "app_mcp",
            "api_base": api_base,
            "appkey": app.get("appkey", ""),
            "sign": app.get("sign", ""),
        }
    # personal_mcp
    token = block.get("token", {}).get("current_token", "")
    return {
        "mode": "personal_mcp",
        "api_base": api_base,
        "app_id": app.get("app_id", ""),
        "ai_description": app.get("ai_description", ""),
        "token_source": f"url:{api_base}/mcp?access_token={token}" if token else "",
    }
