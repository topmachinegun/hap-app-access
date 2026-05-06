"""HAP V3 REST API 客户端（mode=v3_api）。

endpoint: {api_base}/v3/open/<module>/<action>
auth: HTTP header `HAP-Appkey` + `HAP-Sign`（预分发静态字串，无需客户端 HMAC）。

对业务 skill 暴露的调用语义：`call(tool, args)`——其中 `tool` 是 MCP 风格的
工具名，经 TOOL_TO_ENDPOINT 映射到 REST path。映射表在这里集中维护，业务
skill 不需要感知差异。

当 V3 REST 没有对应端点时，raise `UnsupportedTool`，由 CLI 层转为可读错误
（并在 diagnostics 里指出 fallback 方案，如改用 personal_mcp / app_mcp）。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


# MCP 工具名 → V3 REST (path, payload_builder) 映射
# payload_builder(args) 返回 dict，作为 POST body
def _editrow_payload(a: dict) -> dict:
    # MCP update_record 用 fields=[{id, value}]；V3 editRow 用 controls=[{controlId, value}]
    controls = []
    for f in a.get("fields") or a.get("controls") or []:
        controls.append({
            "controlId": f.get("controlId") or f.get("id"),
            "value": f.get("value"),
        })
    return {
        "worksheetId": a.get("worksheetId") or a.get("worksheet_id"),
        "rowId": a.get("rowId") or a.get("row_id"),
        "controls": controls,
    }


def _getfilterrows_payload(a: dict) -> dict:
    return {
        "worksheetId": a.get("worksheetId") or a.get("worksheet_id"),
        "filters": a.get("filters") or [],
        "pageSize": a.get("pageSize") or a.get("page_size") or 50,
        "pageIndex": a.get("pageIndex") or a.get("page_index") or 1,
    }


TOOL_TO_ENDPOINT: dict[str, tuple[str, Any]] = {
    "update_record": ("worksheet/editRow", _editrow_payload),
    "editRow": ("worksheet/editRow", _editrow_payload),
    "get_record_list": ("worksheet/getFilterRows", _getfilterrows_payload),
    "getFilterRows": ("worksheet/getFilterRows", _getfilterrows_payload),
}


class UnsupportedTool(RuntimeError):
    pass


class HapApiClient:
    def __init__(self, profile: dict[str, Any]):
        self.profile = profile
        self.base = (profile.get("api_base") or "https://api.mingdao.com").rstrip("/")
        self.appkey = profile["appkey"]
        self.sign = profile["sign"]
        self.diagnostics: list[str] = []

    def _post(self, path: str, payload: dict) -> Any:
        url = f"{self.base}/v3/open/{path.lstrip('/')}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "HAP-Appkey": self.appkey,
                "HAP-Sign": self.sign,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            self.diagnostics.append(f"[{path}] HTTP {e.code}: {body[:300]}")
            raise
        try:
            obj = json.loads(raw)
        except ValueError:
            self.diagnostics.append(f"[{path}] non-JSON response: {raw[:200]}")
            return raw
        if isinstance(obj, dict):
            if obj.get("success") is False or obj.get("error_code") not in (None, 0):
                self.diagnostics.append(
                    f"[{path}] error_code={obj.get('error_code')} msg={obj.get('error_msg')}"
                )
            return obj.get("data", obj)
        return obj

    def list_tools(self) -> list[str]:
        """v3_api 没有 tools/list；返回映射表 key 列表。"""
        return sorted(TOOL_TO_ENDPOINT.keys())

    def call(self, tool: str, args: dict) -> Any:
        entry = TOOL_TO_ENDPOINT.get(tool)
        if entry is None:
            raise UnsupportedTool(
                f"工具 '{tool}' 在 v3_api mode 下无端点映射。\n"
                f"  支持的工具：{', '.join(sorted(TOOL_TO_ENDPOINT))}\n"
                f"  若需调用其他工具，请切换 profile 到 mode=personal_mcp / app_mcp"
            )
        path, builder = entry
        return self._post(path, builder(args))
