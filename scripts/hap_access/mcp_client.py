"""MCP JSON-RPC 客户端：personal_mcp + app_mcp 共用。

两种 mode 的差异都收敛在 URL 构造与业务参数注入：
  - personal_mcp  : URL 含 Authorization=Bearer <token>；每次业务工具调用
                    必须注入 appId + ai_description
  - app_mcp       : URL 含 HAP-Appkey + HAP-Sign；业务工具调用无需额外注入

对外方法 `call(tool, args)` 对业务 skill 暴露统一语义：
  - args 由业务 skill 传入业务参数
  - 内部根据 mode 自动 merge 鉴权上下文
"""
from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
import uuid
from typing import Any

from .profile import ProfileError


MCP_BASE_DEFAULT = "https://api.mingdao.com/mcp"


class MCPClient:
    def __init__(self, profile: dict[str, Any]):
        self.profile = profile
        self.mode = profile["mode"]
        self.diagnostics: list[str] = []
        self.url = self._resolve_url()
        self._initialized = False

    def _resolve_url(self) -> str:
        url = self.profile.get("mcp_url")
        if url:
            return url
        # personal_mcp + token_source: broker 或 url 直传
        if self.mode == "personal_mcp":
            src = self.profile.get("token_source", "")
            if src.startswith("broker:"):
                key = src.split(":", 1)[1]
                token = self._fetch_broker_token(key)
                base = self.profile.get("api_base") or "https://api.mingdao.com"
                return f"{base}/mcp?Authorization=Bearer%20{urllib.parse.quote(token, safe='')}"
            if src.startswith("url:"):
                return src.split(":", 1)[1]
        # app_mcp 也允许从 appkey+sign+api_base 拼 URL
        if self.mode == "app_mcp":
            base = self.profile.get("api_base") or "https://api.mingdao.com"
            appkey = self.profile["appkey"]
            sign = self.profile["sign"]
            return (
                f"{base}/mcp?HAP-Appkey={urllib.parse.quote(appkey, safe='')}"
                f"&HAP-Sign={urllib.parse.quote(sign, safe='')}"
            )
        raise ProfileError(f"无法从 profile 解析出 MCP URL（mode={self.mode}）")

    def _fetch_broker_token(self, broker_key: str) -> str:
        """调 hap-token broker get 拿当前有效 token。"""
        try:
            r = subprocess.run(
                ["hap-token", "get", broker_key, "--raw"],
                capture_output=True, text=True, timeout=10,
            )
        except FileNotFoundError as e:
            raise ProfileError(
                f"token_source=broker:{broker_key} 要求 hap-token 在 PATH 中\n"
                f"  下一步：install.sh 会把 hap-token symlink 到 ~/.local/bin"
            ) from e
        if r.returncode != 0:
            raise ProfileError(
                f"hap-token get {broker_key} 失败（exit={r.returncode}）：{r.stderr.strip()}"
            )
        return r.stdout.strip()

    def rpc(self, method: str, params: dict | None = None) -> dict:
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method}
        if params is not None:
            body["params"] = params
        req = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
        # SSE 兼容
        if raw.startswith("event:") or "data:" in raw[:40]:
            for line in raw.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
        return json.loads(raw)

    def ensure_initialized(self) -> None:
        if self._initialized:
            return
        self.rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "hap-access", "version": "0.3.0"},
        })
        try:
            self.rpc("notifications/initialized")
        except Exception:
            pass
        self._initialized = True

    def list_tools(self) -> list[str]:
        self.ensure_initialized()
        resp = self.rpc("tools/list")
        tools = resp.get("result", {}).get("tools", []) or []
        return [t.get("name", "") for t in tools if t.get("name")]

    def call(self, tool: str, args: dict) -> Any:
        """调业务工具，自动注入 mode 所需的鉴权上下文。"""
        self.ensure_initialized()
        merged = dict(args)
        if self.mode == "personal_mcp":
            merged.setdefault("appId", self.profile["app_id"])
            merged.setdefault("ai_description", self.profile["ai_description"])
        resp = self.rpc("tools/call", {"name": tool, "arguments": merged})
        content = resp.get("result", {}).get("content", [])
        parsed: list[Any] = []
        for c in content:
            if c.get("type") == "text":
                t = c.get("text", "")
                try:
                    parsed.append(json.loads(t))
                except Exception:
                    parsed.append(t)
            else:
                parsed.append(c)
        # 明道云每条返回包一层 data/error_code
        for item in parsed:
            if isinstance(item, dict):
                if item.get("success") is False or item.get("error_code") not in (None, 0):
                    self.diagnostics.append(
                        f"[{tool}] error_code={item.get('error_code')} "
                        f"msg={item.get('error_msg') or item.get('error')}"
                    )
                if "data" in item:
                    return item["data"]
        return parsed
