"""hap-access CLI: 业务 skill 调用入口。

子命令：
  call          : 调业务工具（最核心）
  list-tools    : 列出当前 profile 可用的 MCP 工具（探针用）
  profile       : profile 管理（--list / --show / --validate / --init）

stdout 统一返 JSON：
  成功：{"ok": true,  "mode": "...", "data": ..., "diagnostics": [...]}
  失败：{"ok": false, "mode": "...", "error": "...", "diagnostics": [...]}

退出码：0=成功，1=业务失败，2=用法错误/profile 非法
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from typing import Any

from . import profile as profile_mod
from .api_client import HapApiClient, UnsupportedTool
from .mcp_client import MCPClient
from .profile import ProfileError


def _ok(mode: str, data: Any, diags: list[str]) -> int:
    print(json.dumps(
        {"ok": True, "mode": mode, "data": data, "diagnostics": diags},
        ensure_ascii=False, indent=2,
    ))
    return 0


def _fail(mode: str, err: str, diags: list[str] | None = None, code: int = 1) -> int:
    print(json.dumps(
        {"ok": False, "mode": mode, "error": err, "diagnostics": diags or []},
        ensure_ascii=False, indent=2,
    ))
    return code


def _make_client(prof: dict[str, Any]):
    mode = prof["mode"]
    if mode in ("personal_mcp", "app_mcp"):
        return MCPClient(prof)
    if mode == "v3_api":
        return HapApiClient(prof)
    raise ProfileError(f"未知 mode={mode}")


def cmd_call(args: argparse.Namespace) -> int:
    try:
        prof = profile_mod.load(args.profile)
    except ProfileError as e:
        return _fail("unknown", str(e), code=2)
    try:
        tool_args = json.loads(args.args) if args.args else {}
    except json.JSONDecodeError as e:
        return _fail(prof["mode"], f"--args 不是合法 JSON：{e}", code=2)
    cli = _make_client(prof)
    try:
        data = cli.call(args.tool, tool_args)
    except UnsupportedTool as e:
        return _fail(prof["mode"], str(e), cli.diagnostics, code=2)
    except Exception as e:
        return _fail(prof["mode"], f"{type(e).__name__}: {e}", cli.diagnostics)
    return _ok(prof["mode"], data, cli.diagnostics)


def cmd_list_tools(args: argparse.Namespace) -> int:
    try:
        prof = profile_mod.load(args.profile)
    except ProfileError as e:
        return _fail("unknown", str(e), code=2)
    cli = _make_client(prof)
    try:
        tools = cli.list_tools()
    except Exception as e:
        return _fail(prof["mode"], f"{type(e).__name__}: {e}", cli.diagnostics)
    return _ok(prof["mode"], {"tools": tools, "count": len(tools)}, cli.diagnostics)


def cmd_profile(args: argparse.Namespace) -> int:
    if args.list:
        names = profile_mod.list_profiles()
        print(json.dumps({"ok": True, "profiles": names}, ensure_ascii=False, indent=2))
        return 0
    if args.show:
        try:
            prof = profile_mod.load(args.show)
        except ProfileError as e:
            return _fail("unknown", str(e), code=2)
        print(json.dumps(
            {"ok": True, "profile": profile_mod.redact(prof)},
            ensure_ascii=False, indent=2,
        ))
        return 0
    if args.validate:
        try:
            prof = profile_mod.load(args.validate)
        except ProfileError as e:
            return _fail("unknown", str(e), code=2)
        # 探针：尝试 list_tools 看连通性
        cli = _make_client(prof)
        try:
            if prof["mode"] != "v3_api":
                cli.list_tools()
        except Exception as e:
            return _fail(prof["mode"], f"连通性探针失败：{type(e).__name__}: {e}", cli.diagnostics)
        return _ok(prof["mode"], {"validate": "ok", "name": args.validate}, cli.diagnostics)
    if args.init:
        return _profile_init_wizard()
    print("ERROR: 至少提供 --list / --show / --validate / --init 之一", file=sys.stderr)
    return 2


def _profile_init_wizard() -> int:
    print("hap-access profile 初始化向导（Ctrl-C 取消）", file=sys.stderr)
    name = input("profile name（英文）: ").strip()
    if not name:
        return 2
    mode = input("mode [personal_mcp/app_mcp/v3_api]: ").strip()
    if mode not in profile_mod.VALID_MODES:
        print(f"非法 mode={mode}", file=sys.stderr)
        return 2
    data: dict[str, Any] = {"name": name, "mode": mode,
                            "api_base": "https://api.mingdao.com"}
    if mode == "personal_mcp":
        data["app_id"] = input("app_id: ").strip()
        data["ai_description"] = input("ai_description（180 字内）: ").strip()[:180]
        print("选择 token 来源：1) 直接粘 mcp_url   2) 对接 broker", file=sys.stderr)
        choice = input("[1/2]: ").strip()
        if choice == "1":
            data["mcp_url"] = input("完整 MCP URL: ").strip()
        else:
            key = input("broker profile key（如 claw-crm）: ").strip()
            data["token_source"] = f"broker:{key}"
    else:
        data["appkey"] = getpass.getpass("appkey: ")
        data["sign"] = getpass.getpass("sign: ")
    try:
        path = profile_mod.save(name, data)
    except ProfileError as e:
        return _fail("unknown", str(e), code=2)
    print(json.dumps({"ok": True, "saved": str(path)},
                     ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hap-access",
                                description="HAP 应用通用访问 CLI（hap-app-access v0.3.0）")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("call", help="调业务工具")
    c.add_argument("--profile", required=True)
    c.add_argument("--tool", required=True)
    c.add_argument("--args", default="{}",
                   help='业务参数 JSON，如 \'{"query":"..."}\'（默认 {}）')
    c.set_defaults(func=cmd_call)

    lt = sub.add_parser("list-tools", help="列出可用工具")
    lt.add_argument("--profile", required=True)
    lt.set_defaults(func=cmd_list_tools)

    pr = sub.add_parser("profile", help="profile 管理")
    pr.add_argument("--list", action="store_true")
    pr.add_argument("--show", metavar="NAME")
    pr.add_argument("--validate", metavar="NAME")
    pr.add_argument("--init", action="store_true")
    pr.set_defaults(func=cmd_profile)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
