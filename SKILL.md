---
name: hap-app-access
description: 明道云 HAP 应用通用访问技能，覆盖两种授权类型（应用级 Appkey+Sign / 个人级 OAuth Bearer）与两种调用路径（MCP 协议 / V3 REST API）的交叉组合。当用户需要"访问明道云应用"、"连接 HAP 应用"、"读写 HAP 数据"、"选择授权方式"、"MCP 和 API 怎么选"等场景时使用。不包含具体业务逻辑，只提供通用的授权、连接、调用方法论与陷阱清单。
license: MIT
---

# HAP 应用通用访问技能

本技能提供访问明道云（HAP）应用的**通用方法论**：两种授权类型 × 两种调用路径的完整矩阵，帮助 AI 快速判断和实施正确的访问方式。

---

## 1. 授权类型总览

HAP 应用有且仅有两种授权类型，决定了**谁能访问**和**能访问什么**：

| 维度 | 应用级授权（Appkey+Sign） | 个人级授权（OAuth Bearer） |
|------|--------------------------|---------------------------|
| 身份 | 应用身份（不受人约束） | 个人身份（等同于登录用户） |
| 凭证 | Appkey + Sign（长期有效） | Bearer Token（约 1 天过期） |
| 权限范围 | 应用内 API 开关控制的全部数据 | 当前登录用户在应用中可见的数据 |
| 跨应用 | 只能访问所属应用 | 可跨应用访问用户有权限的所有应用 |
| 适用场景 | 后台定时任务、服务间同步、脚本自动化 | 个人数据查询、以用户视角读写数据 |
| 过期 | 不过期（除非在 HAP 后台重置） | 约 1 天，需要刷新机制 |
| 获取位置 | HAP 后台 → 应用 → API 开发 → API 密钥 | OAuth 授权流程（见 §2.2） |

**选择原则**：
- 需要**无人值守运行** → 应用级（Appkey+Sign）
- 需要**受用户权限约束** → 个人级（OAuth Bearer）
- 需要跨多个应用 → 个人级（一个 token 覆盖多应用）
- 两者都可用 → 优先应用级（无过期风险）

---

## 2. 两种调用路径

拿到授权后，有两条路径调用 HAP：

| 维度 | MCP 协议（SSE/Streamable HTTP） | V3 REST API（HTTP JSON） |
|------|-------------------------------|-------------------------|
| 协议 | MCP（Model Context Protocol） | 标准 HTTPS + JSON |
| 端点 | `https://api.mingdao.com/mcp` | `https://api.mingdao.com/v3/open/...` |
| 鉴权注入 | URL query 参数或 SSE Header | HTTP 请求头 |
| 工具发现 | 自动暴露 40~70 个工具 | 需查 API 文档 |
| 调用方式 | AI 工具原生支持（如 Qoder/Cursor 的 MCP 集成） | 代码中 `fetch`/`requests` 等 |
| 适合谁 | AI 助手直接操作数据 | 开发者在代码中集成 |
| 分页 | `pageSize` 上限 **90** | `pageSize` 上限 **1000** |
| 响应大小 | 单次约 **256KB** 缓冲上限 | 无此限制 |

**选择原则**：
- AI 在对话中直接操作数据 → MCP
- 写代码（前端/后端/脚本）集成 HAP → V3 REST API
- 两者都能用 → AI 场景用 MCP，代码场景用 V3 API

---

## 3. 交叉矩阵：2×2 = 4 种组合

|  | MCP 协议 | V3 REST API（`/v3/open/*`） |
|--|---------|-------------|
| **应用级 Appkey+Sign** | ✅ 最常用，配置简单 | ✅ 代码集成首选 |
| **个人级 OAuth Bearer** | ✅ **推荐且强制**：以 MCP 为首选 | ❌ `/v3/open/*` 仅认 Appkey+Sign |

> **路径优先级（Personal OAuth）**：官方 Personal MCP 会持续升级工具集与 schema，本技能**强制默认走 MCP 协议**（通过 `tools/list` 发现 + `tools/call` 调用）。Personal OAuth 底层另有一套独立于 `/v3/open/*` 的 REST 接口族（即 Integration Connect 页面上的 Actions，与 MCP 共享同一份 schema），但本技能**不推荐直连 REST**——避免官方升级时字段或端点变化导致脚本断裂。详见 §5.6。

---

## 4. 应用级授权：Appkey+Sign

### 4.1 获取凭证

1. 登录 HAP → 进入目标应用 → **应用设置** → **API 开发** → **API 密钥**
2. 复制 `Appkey` 和 `Sign`
3. 或复制 MCP URL：`https://api.mingdao.com/mcp?HAP-Appkey=<Appkey>&HAP-Sign=<Sign>`

### 4.2 MCP 路径配置

在 AI 工具的 MCP 配置中写入：

```json
{
  "mcpServers": {
    "hap-mcp-<应用名>": {
      "url": "https://api.mingdao.com/mcp?HAP-Appkey=<Appkey>&HAP-Sign=<Sign>"
    }
  }
}
```

配置后可用的典型工具（约 40 个）：
- `get_app_info` / `get_app_worksheets_list` / `get_worksheet_structure`
- `get_record_list` / `get_record_details` / `get_record_pivot_data`
- `create_record` / `update_record` / `delete_record`
- `batch_create_records` / `batch_update_records` / `batch_delete_records`

> 配置步骤详见 `hap-mcp-usage` 技能。

### 4.3 V3 REST API 路径

**请求头**：

```http
Content-Type: application/json
HAP-Appkey: <Appkey>
HAP-Sign: <Sign>
```

**常用端点**：

| 操作 | 方法 | 路径 |
|------|------|------|
| 获取应用信息 | GET | `/v3/app/info` |
| 获取工作表列表 | GET | `/v3/app/worksheets` |
| 获取工作表字段 | GET | `/v3/app/worksheet/getFields` |
| 查询记录 | POST | `/v3/app/worksheets/{id}/rows/list` |
| 获取记录详情 | GET | `/v3/app/worksheets/{id}/rows/{rowId}` |
| 创建记录 | POST | `/v3/app/worksheets/{id}/rows` |
| 更新记录 | PUT | `/v3/app/worksheets/{id}/rows/{rowId}` |
| 删除记录 | DELETE | `/v3/app/worksheets/{id}/rows/{rowId}` |
| 批量创建 | POST | `/v3/app/worksheets/{id}/rows/batch` |
| 批量更新 | PUT | `/v3/app/worksheets/{id}/rows/batch` |
| 批量删除 | DELETE | `/v3/app/worksheets/{id}/rows/batch` |
| 获取关联记录 | GET | `/v3/app/worksheets/{id}/rows/{rowId}/relations/{fieldId}` |
| 查找用户 | POST | `/v3/users/lookup` |
| 查找部门 | POST | `/v3/departments/lookup` |

**示例（查询记录）**：

```python
import requests

headers = {
    "Content-Type": "application/json",
    "HAP-Appkey": "<Appkey>",
    "HAP-Sign": "<Sign>",
}

payload = {
    "pageSize": 50,
    "pageIndex": 1,
    "useFieldIdAsKey": True,
    "filter": {
        "type": "group",
        "logic": "AND",
        "children": [
            {
                "type": "condition",
                "field": "<fieldId>",
                "operator": "eq",
                "value": ["<value>"],
            }
        ],
    },
}

resp = requests.post(
    "https://api.mingdao.com/v3/app/worksheets/<worksheetId>/rows/list",
    headers=headers,
    json=payload,
)
data = resp.json()
```

> 完整 API 规范详见 `hap-v3-api` 技能。

---

## 5. 个人级授权：OAuth Bearer

### 5.1 获取 Token

1. 在 HAP 组织管理后台创建 **OAuth 应用**（获取 `client_id` / `client_secret`）
2. 通过 OAuth 授权码流程或资源所有者密码凭据流程获取 Bearer Token
3. 或使用 `hap-oauth-mcp` 技能自动完成授权 + 生成 MCP 配置

### 5.2 MCP 路径配置

```json
{
  "mcpServers": {
    "HAP-Personal-MCP": {
      "url": "https://api.mingdao.com/mcp?Authorization=Bearer%20<Token>"
    }
  }
}
```

配置后可用的典型工具（约 60~70 个）：
- 涵盖应用级的全部工具
- 额外包含：`get_org_list`（组织列表）、跨应用数据访问等
- 受用户权限约束：只能看到用户有权限的应用和工作表

### 5.3 MCP 调用必填参数

Personal MCP 的**每次工具调用**必须额外提供：

```json
{
  "appId": "<目标应用的 AppID>",
  "ai_description": "<本次调用的用途描述>",
  "worksheetId": "<工作表 ID>",
  "...": "其他业务参数"
}
```

- `appId`：必填，标识访问哪个应用，否则返回 401
- `ai_description`：必填，HAP 服务端用于审计和鉴权校验，否则返回 401

> 应用级 MCP 不需要这两个参数——Appkey+Sign 已经绑定了应用。

### 5.4 获取应用 AppID

Personal MCP 调用需要 `appId`，但用户可能不知道目标应用的 AppID。获取方式：

| 方式 | 说明 | 适用场景 |
|------|------|----------|
| 浏览器 URL | 打开目标应用，URL 格式 `https://app.mingdao.com/app/<AppID>/...` | 已知应用名，手动查看 |
| MCP 发现序列 | `get_org_list()` → `get_app_list(org_id)` → 按名称匹配 | 代码/脚本自动化（详见 §5.7） |
| V3 API `GET /v3/app/info` | 使用 Appkey+Sign 请求，返回 `data.appId` | 已有应用级凭证 |

> **`get_app_list` 的参数是 `org_id`（不是 `appId`）**。必须先调 `get_org_list()` 拿到组织 ID，再传给 `get_app_list`。不传或传错会返回 `error_code: 10001`，详见 §8.12。

### 5.5 Token 过期与刷新

Bearer Token 有效期约 **1 天**，过期后所有 Personal MCP 调用返回鉴权失败。

**刷新策略**（由使用者自行实现，本技能不展开具体代码）：

| 策略 | 描述 | 适合场景 |
|------|------|---------|
| 主动检测 | 调用前检查 token 的 `expires_at` / `refreshed_at`，提前刷新 | 定时任务、长时间运行的脚本 |
| 被动重试 | 调用返回鉴权失败时，自动刷新 token 并重试一次 | **必须开启**，详见下方说明 |
| 手动刷新 | 使用 `hap-oauth-mcp` 技能重新生成 MCP 配置 | 偶尔使用、调试 |

**鉴权失败的典型表现**：
- `isError: true` + `error_code: 600101`（授权已失效）
- 响应包含 `token无效` / `token过期` / `Authorization failed` 等关键词
- `success: false`

> `hap-oauth-mcp` 技能提供了 Token 刷新的完整实现参考。
>
> **重要：被动重试不能关闭**。仅靠主动检测（检查 `refreshed_at`）无法覆盖「token 未超龄但服务端已提前失效」的场景——服务端可因密码变更、OAuth 授权撤销等原因随时让 token 失效，此时主动检测判断为"未过期"不会触发刷新，若无被动兜底则所有后续调用连续 FATAL。因此被动重试是不可或缺的第二道防线，不应关闭。

#### 5.5.1 刷新 = 重跑一次完整登录（没有轻量路径）

`hap-oauth-mcp` 技能的「刷新」命令和「首次生成」是**同一条命令**（`md-generate-mcp-config`），都需要账号 + 密码 + OAuth App id。没有「拿 refresh_token 换新 access_token」这种轻量路径——所有 token 都是走一次完整 OAuth 登录流程拿到的。

**含义**：

- Agent 每次刷新前都需要账号密码，**这是设计，不是缺陷**
- 用户不要期望「一次输入永远不用再输」，除非设置 env var（见 §5.5.2）
- 「刷新失败」不等于「密码错」，具体归因见 §5.5.3

#### 5.5.2 密码的安全边界（为什么不让 Agent 记住密码）

三种凭证的泄露影响和允许落地位置不同，**密码是最敏感的一类**：

| 凭证 | 泄露影响 | 允许落地的位置 |
|---|---|---|
| **密码** | 主密钥，可无限签发新 token，影响永久 | 仅 env var `MINGDAO_PASSWORD` / 交互时现贴现忘 |
| Bearer token | 跨多 app 的用户身份，但 1 天自动失效 | MCP JSON 本机落盘可接受；**禁止提交 git / 发群** |
| Appkey+Sign | 单应用长期凭证 | 同上 |

**禁止路径（针对密码）**：写进对话历史（会进入模型上下文、被转录、被其他 Agent 读到）、写进回复文本、写进日志、写进任何会被 LLM 看到的文件。

**标准做法**：让用户把 `MINGDAO_ACCOUNT` / `MINGDAO_PASSWORD` 加进 shell profile（`~/.zshrc` 或 `~/.bashrc`，一次性动作），Agent 调脚本时由 env 注入，**不经过对话**。既避免用户反复输入，也不让密码进入 LLM 上下文。

> 纪律：Agent 遇到 token 失效时，如果 env 未设，应主动问用户要密码——【这是预期行为，不要报错为「密码错」】。

#### 5.5.3 刷新失败的 5 类真实原因（禁止默认甩锅「密码错」）

| 征兆 | 真实原因 | 处置 |
|---|---|---|
| 登录接口返回 invalid credentials | 密码真的错/改了 | 请用户确认最新密码 |
| authorize 403 / 拿不到 `oauth2Url` | OAuth App 被管理员撤销授权 | 联系 HAP 管理员重新授权 |
| 拿到 token，但调具体 app 时 401 | OAuth App 白名单未包含该 app（见 §8.5） | 在 HAP 后台把该 app 加入 OAuth App 授权范围 |
| 登录直接被拒（短时间内多次失败） | 账号已被风控锁定 | 等待冷却或联系管理员解锁 |
| 网络超时 / SSL / DNS | 域名不对（私有化部署） | 设 `MINGDAO_API_BASE_URL` 覆盖默认 `api.mingdao.com` |

> **纪律**：Agent 报「密码错」前，必须先看脚本 stderr 里的真实错误码 / 接口名，按上表归因。默认甩锅密码会误导用户重置密码，而真原因可能是白名单 / 撤权 / 风控锁定。

### 5.6 调用路径选择：强制走 MCP 协议

Personal OAuth Bearer 的访问形态有三种，本技能**只推荐第一种**：

| 形态 | 说明 | 本技能态度 |
|------|------|------------|
| MCP 协议（`tools/list` + `tools/call`） | 官方一等公民，持续升级新工具；握手时自动协商 schema | ✅ **首选** |
| 新 REST 接口族（Integration Connect 页面上的 `/app/*` Actions） | 与 MCP 共享同一份 schema（1:1），但直连 REST 需自己处理 `HAP-Appid` header、错误码映射等 | ⚠️ **不推荐**，本技能不覆盖；官方升级时最易断裂 |
| 传统 V3 REST API（`/v3/open/*`） | **仅认 Appkey+Sign**，OAuth Bearer 在此族完全不可用 | ❌ 不适用 |

**结论**：Personal OAuth 场景下，智能体统一通过 MCP 协议调用工具；当客户端未集成 MCP 时，用 §5.7 的 Python SDK 或 curl JSON-RPC 做运行时直调——**仍然走 MCP 协议**，不要直连任何 REST 端点。

### 5.7 官方应用访问最佳实践

对于**明道云官方应用**（CRM2025、明道云知识库等），应用管理员为明道官方团队，**外部用户无法获取 Appkey+Sign**，因此只能走 Personal OAuth（详见 §8.11）。本节提供从零到拿到数据的标准路径，包含「不依赖客户端 MCP 集成」的运行时直调方案。

#### 标准发现序列 (5 步)

```
1. get_org_list()                                 → 拿所有可见组织 org_id
2. get_app_list(org_id)                           → 按名称定位目标应用 appId
3. get_app_worksheets_list(appId)                 → 列出应用所有工作表
4. get_worksheet_structure(                       → 查字段与选项 key
     worksheet_id, appId,
     responseFormat="md")
5. get_record_list(                               → 按条件取数据
     worksheet_id, appId, filter, fields)
```

关键点：
- `get_app_list` 参数是 **`org_id`**；`get_worksheet_structure` / `get_record_list` 的工作表参数是 **`worksheet_id`**（snake_case）——命名混用见 §7.1
- 每次调用必填 `ai_description`；**业务工具**（`get_record_list` 等）需加 `appId`，**元数据工具**（`get_org_list` 等）不需
- `get_worksheet_structure` 建议传 `responseFormat="md"`，输出紧凑且含选项 key

#### 运行时直调：Python MCP SDK

当客户端（Qoder / Cursor / 自建智能体等）未集成 MCP 或不方便重启时，可用 MCP Python SDK 在临时脚本中直接调用：

```python
# pip install mcp
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = "https://<host>/mcp?Authorization=Bearer%20<Token>"

async def call(tool_name, args):
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool_name, args)

# 示例 1：元数据工具 — 不需 appId
asyncio.run(call("get_org_list", {"ai_description": "list orgs"}))

# 示例 2：业务工具 — 需 appId + ai_description
asyncio.run(call("get_record_list", {
    "appId": "<appId>",
    "worksheet_id": "<worksheetId>",
    "pageSize": 50,
    "ai_description": "query records",
}))
```

- `<host>` 按 §6 域名规则：**明道云官方过渡期集成 App** 挂在 `api2.mingdao.com`；**自建 OAuth App** 依白名单而定（默认 `api.mingdao.com`），详见 §8.5
- **Token 包含于 URL 中勿提交至版本库**；预期长期复用时，推荐从环境变量读取

#### 运行时直调：curl JSON-RPC（备选）

不方便装 Python 时，可用 curl 发原始 JSON-RPC：

```bash
# 1. initialize（响应 Header 会返回 mcp-session-id，后续所有调用必须带）
curl -i -X POST "https://api2.mingdao.com/mcp?Authorization=Bearer%20<Token>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json,text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'

# 2. tools/call
curl -X POST "https://api2.mingdao.com/mcp?Authorization=Bearer%20<Token>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json,text/event-stream" \
  -H "mcp-session-id: <上一步返回的 session id>" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_org_list","arguments":{"ai_description":"list orgs"}}}'
```

响应为 SSE 格式，需解析 `data: ` 行。如需交互式调试，可使用 `npx @modelcontextprotocol/inspector`。

### 5.8 定位官方应用

本技能不内置官方应用的 appId 白名单（官方应用可能调整，且不同组织可见性不同）。按需定位的推荐做法：

1. **浏览器 URL法**：登录 HAP Web 端 → 打开目标应用 → 地址栏 `https://app.mingdao.com/app/<appId>/...` 直接拿
2. **发现序列法**：按 §5.7 执行 `get_org_list` → `get_app_list(org_id)` 后，在返回的 app 列表中按 `name` 关键词（如 `"CRM"` / `"知识库"`）模糊匹配
3. **官方知识库特则**：`knowledge_search` 在部分 token 下返回「账号未登录」，改走 `get_app_worksheets_list` → `get_record_list`，详见 §8.14

---

### 5.9 Token 自动化管理脚本（`scripts/mcp_token.py`）

本仓库 `scripts/mcp_token.py` 是个人级 OAuth Token 的**透明管理器**，供下游 skill（如 `crm-project-review`）和业务脚本复用。它解决三个痛点：

1. **token 1 天过期**但不该让 Agent / 用户每次手动刷新
2. **密码不能进对话**（见 hap-oauth-mcp §Token 生命周期）——脚本从 env 读凭证，Agent 只看到一个 URL输出
3. 下游脚本不应该重复实现「调 md-generate → 缓存 → 判过期」逻辑

#### 用法

```bash
# 一次性写进 shell profile (~/.zshrc / ~/.bashrc)
export MINGDAO_ACCOUNT='13800138000'      # 11 位手机号会自动补 +86；email 原样
export MINGDAO_PASSWORD='your_password'
# export MINGDAO_OAUTH_APP_ID='...'         # 可选；默认 ClawCRM SaaS 官方
export HAP_APP_ACCESS_DIR=~/Desktop/hap-app-access  # 可选；脚本默认探测几个常见路径

# CLI
python3 $HAP_APP_ACCESS_DIR/scripts/mcp_token.py            # 打印当前有效 URL（必要时自动刷新）
python3 $HAP_APP_ACCESS_DIR/scripts/mcp_token.py --refresh  # 强制刷新
python3 $HAP_APP_ACCESS_DIR/scripts/mcp_token.py --status   # 查看缓存状态（脱敏）
```

#### 下游 Python 调用

**推荐 subprocess 零耦合（跨 skill 不依赖 sys.path / pip install）**：

```python
import os, subprocess, sys
from pathlib import Path

hap_dir = os.environ.get("HAP_APP_ACCESS_DIR") or str(Path.home() / "Desktop/hap-app-access")
url = subprocess.check_output([sys.executable, f"{hap_dir}/scripts/mcp_token.py"], text=True).strip()
# 使用 url 调 MCP。脚本保证返回的 URL 已 URL-encode（Bearer 后面的空格是 %20）
```

#### 设计要点

| 属性 | 值 |
|---|---|
| 凭证来源 | env `MINGDAO_ACCOUNT` / `MINGDAO_PASSWORD` / `MINGDAO_OAUTH_APP_ID`（默认 ClawCRM）|
| 缓存路径 | env `HAP_MCP_CACHE_DIR` 覆盖 > `~/.cache/hap-mcp/token.json` > `/tmp/hap-mcp/token.json`（sandbox 受限自动回退）|
| 过期阈值 | fetched_at + 23h（留 1h buffer，token 实际寿命 ~24h）|
| 刷新后端 | 调 `~/.qoder/skills/hap-oauth-mcp/.venv/bin/md-generate-mcp-config`（必需先安装 hap-oauth-mcp skill）|
| 手机号处理 | 11 位以 1 开头的纯数字自动补 `+86` 前缀（md-generate 要求 E.164）|
| URL encode | `Bearer ` 空格自动转 `Bearer%20`（避免 Python urllib InvalidURL）|
| 失败脱敏 | 报错不含密码/token，stderr 只走 `MCPCredentialError`提示仓 |

#### 与 hap-oauth-mcp 的边界

- **hap-oauth-mcp**：负责“一次性 OAuth 授权 + 首次生成 MCP JSON”，文档面向人（用户手动跑）
- **本脚本**：负责“复用凭证、缓存 token、过期自动刷新”，面向代码（下游脚本调用）

两者互补：用户首次跑 `md-generate-mcp-config` 完成授权后，后续所有下游脚本都走 mcp_token 透明获取，再也不需要 Agent 介入凭证流转。

---

## 6. API Host（产品线）

HAP 支持多个产品线和私有部署，**API Host 不同**：

| 产品线 | API Host | MCP URL 示例 |
|--------|----------|-------------|
| 明道云 HAP | `https://api.mingdao.com` | `https://api.mingdao.com/mcp?...` |
| Nocoly HAP | `https://www.nocoly.com` | `https://www.nocoly.com/mcp?...` |
| 私有部署 | `https://<域名>/api` | `https://<域名>/mcp?...` |

> 私有部署的 V3 API 路径需在域名后加 `/api`（如 `https://p-demo.mingdaoyun.cn/api/v3/...`），MCP 端点则直接挂在根域名下。

---

## 7. 通用调用规范（MCP + V3 API 共用）

### 7.1 参数命名：以 `tools/list` 为唯一权威来源（SSOT）

HAP 工具参数命名**混用 camelCase 和 snake_case**。**根因不是 MCP 做了命名转换**，而是 **Personal MCP 底层每个 Action 由 integration 作者各自定义**，同一 MCP 内不同工具的风格可能不同。

| 命名风格 | 代表参数 |
|---------|---------|
| camelCase | `pageSize`、`pageIndex`、`useFieldIdAsKey`、`appId`、`responseFormat`、`knowledgeIds`、`searchMode`、`topK` |
| snake_case | `org_id`、`worksheet_id`、`row_id`、`view_id` 等**资源 ID 类**；`ai_description`（一线必填法定参数） |

**铁律**：调用任何工具前，**先执行一次 `tools/list` 取回目标工具的 `inputSchema`，严格以 schema 声明的 key 名传参**。不要照搬文档、不要按常识猜参数、不要把上游返回字段直接当下游 key（见 §8.15）。

**为什么 `tools/list` 是 SSOT**：
1. 官方 Personal MCP 持续升级，`tools/list` 永远反映**当前运行时**的真实接口
2. `tools/list` 输出等价于 Integration Connect 页面上该 Action 的字段定义——二者同源
3. 再强的直觉也比不上 schema 的 `"required": ["worksheet_id"]` 一行

**获取 schema 的三种方式**：
- 交互式：`npx @modelcontextprotocol/inspector` 连接 MCP URL 后在 UI 查看
- 脚本化：Python MCP SDK `session.list_tools()`（模板见 §5.7）
- 底层：curl 发 `{"method":"tools/list"}` 的 JSON-RPC

**陷阱案例**：
- `get_worksheet_structure(worksheetId=...)` → ❌ 报 "Map has no value for 'worksheet_id'"
- `get_worksheet_structure(worksheet_id=...)` → ✅

### 7.2 Filter 结构

```json
{
  "filter": {
    "type": "group",
    "logic": "AND",
    "children": [
      {
        "type": "condition",
        "field": "<fieldId 或 alias>",
        "operator": "eq",
        "value": ["<值>"]
      }
    ]
  }
}
```

规则：
- 顶层必须是 `group`
- 最多两层嵌套：`group → group → condition`
- `operator` 是字符串：`"eq"` / `"in"` / `"between"` / `"contains"` / `"belongsto"` 等

### 7.3 分页

| 路径 | pageSize 上限 | 推荐值 | 说明 |
|------|-------------|--------|------|
| MCP `get_record_list` | **90** | 50 | 单次响应有 ~256KB 缓冲上限，大表必须降 page_size |
| V3 API `rows/list` | **1000** | 100~500 | 无缓冲限制，但不宜过大 |

必须翻页获取全部记录，**不可用单页数据做全局统计**。

### 7.4 字段 ID vs 别名

| 场景 | 用什么 |
|------|--------|
| Filter 的 `field` | fieldId（UUID）或 alias 均可 |
| 写入（create/update）的 key | fieldId 或 alias 均可 |
| `get_record_list(useFieldIdAsKey=True)` 返回的 key | **强制替换为 fieldId（UUID）**，即使字段有 alias |

> 如果 `useFieldIdAsKey=True`，读取时必须用 UUID 做 key，否则取不到值。这是最常见的踩坑点之一。

---

## 8. 通用陷阱清单

### 8.1 选项字段写入必须用 key

写入 SingleSelect / MultipleSelect 字段时，value 必须传 **option key（UUID）** 的数组，不能传显示文本。

```json
// ✅ 正确
{ "field": "status", "value": ["74c7b607-864d-4cc4-b401-28acba2636e9"] }

// ❌ 错误
{ "field": "status", "value": ["已完成"] }
```

即使是单选，也要用数组 `["key"]`。

### 8.2 关联字段 get_record_list 可能丢失

`get_record_list` 对部分 Relation 字段（典型：多层关联、子表关联）可能返回空字符串 `""`，即使后端确实挂了关联。

**解法**：对空值关联字段，额外调 `get_record_details(rowId)` 补全。

### 8.3 _owner 字段响应为空但 filter 有效

`_owner` 字段在记录列表/详情中永远返回 `""`，但 `filter.ownerid` 筛选仍然有效。

**解法**：需要 owner 信息时，从 `_createdBy.accountId` 或工作流回推获取；筛选照用 `ownerid`。

### 8.4 caid 服务端 filter 的 in 操作不稳定

服务端 `filter.field_id=caid` 对数组的 `in` 操作支持有限（部分网关直接忽略数组参数）。

**解法**：客户端过滤——先拉全量再按 `_createdBy.accountId` 在客户端筛选。

### 8.5 OAuth Bearer 域名白名单

OAuth App 的 Bearer Token 只对**创建该 App 时配置的域名**鉴权有效，不同 OAuth App 的白名单域名不同：

| OAuth App 类型 | 域名白名单 | 典型场景 |
|---------------|----------|---------|
| **明道云官方过渡期集成 App** | `api2.mingdao.com` | 使用 `hap-oauth-mcp` 技能或官方授权链接获取 token |
| **自建 OAuth App（默认配置）** | `api.mingdao.com` | 企业自主集成、开发者自己注册的 App |

- 调错域名 → 返回 `error_code: 10001 Http Headers verification failed`
- 两个域名**不可互换**：官方 token 调 `api.mingdao.com` 会 10001，自建 token 调 `api2.mingdao.com` 也会 10001

**解法**：
1. 先确认 token 来源：官方过渡期集成 → `api2.mingdao.com`；自建 → `api.mingdao.com`（或 OAuth App 配置的自定义域名）
2. MCP URL 和 V3 API（如可用）必须使用对应域名
3. `tools/list` 通过但 `tools/call` 10001：先查是否漏传参数（见 §8.12），再查域名白名单

### 8.6 MCP 单次响应 256KB 上限

MCP 协议的单次响应有约 256KB 的缓冲上限，超出抛 `Exceeded limit on max bytes to buffer`。

**解法**：降低 `pageSize`（大表推荐 50），或改用 V3 REST API。

### 8.7 数值字段读写类型不一致

- 写入：传数字类型 `1000000.50`
- 读取：返回字符串 `"1000000.50"`

**解法**：比对时需注意类型转换。

### 8.8 日期过滤时区偏移

日期字段可能因服务端时区设置偏移 ±1 天。

**解法**：放宽过滤窗口（`start-1 ~ end+1`）+ 客户端二次过滤。

### 8.9 triggerWorkflow 参数

创建/更新/删除记录时，`triggerWorkflow` 控制是否触发 HAP 工作流：

| 场景 | 值 |
|------|---|
| 正常业务操作 | `true`（默认） |
| 数据迁移 / 批量同步 / 测试 | `false` |

### 8.10 Personal MCP 的 appId 和 ai_description

应用级 MCP 调用不需要这两个参数。**个人级 MCP 的每次调用必须提供**，否则返回 401。

### 8.11 官方应用不支持 Appkey+Sign

**明道云官方应用**（CRM2025、明道云知识库等）的应用管理员为明道官方团队，**外部用户无法获取其 Appkey 和 Sign**。

**表现**：尝试按 §4.1 的步骤打开官方应用时，找不到「API 开发」入口或无权限查看。

**解法**：官方应用只能通过 **Personal OAuth Bearer** 访问（详见 §5 与 §5.7）。如业务场景要求「无人值守」（定时任务/脚本自动化），需用自己的 HAP 账号/密码通过 `hap-oauth-mcp` 自动刷新 token，并接受 token 约 1 天过期的限制。

### 8.12 Personal MCP 的 get_app_list 参数是 org_id

`get_app_list` 的参数是 **`org_id`**（组织 ID，snake_case），不是 `appId`。不传或传错会返回 `error_code: 10001 Http Headers verification failed`，不是缺少参数的提示，容易误判为域名白名单问题。

```json
// ❌ 错误：不传 org_id 返回 10001
{ "ai_description": "list apps" }

// ❌ 错误：传 appId 无效
{ "appId": "<appId>", "ai_description": "list apps" }

// ✅ 正确
{ "org_id": "<orgId>", "ai_description": "list apps" }
```

**解法**：先调 `get_org_list()` 拿到组织 ID，再传给 `get_app_list`。完整发现序列详见 §5.7。

### 8.13 Token 未超龄但服务端已失效

Bearer token 的 `refreshed_at` 仅记录客户端上次刷新时间，不代表服务端一定认可。服务端可因以下原因让 token 提前失效：

- 用户密码变更
- OAuth 授权被管理员撤销
- 服务端安全策略调整

**表现**：主动检测 `is_stale()` 返回 False（未超龄），但所有 MCP 调用返回 `token无效或过期`。

**解法**：必须同时实现主动检测 + 被动重试双保险。仅靠主动检测不够。

### 8.14 knowledge_search 返回「账号未登录」的排查路径

Personal MCP 的 `knowledge_search` 是原生 RAG 语义检索入口（支持 `vector` / `keyword` / `hybrid` 三种模式），但对部分 token / 部分调用会返回「账号未登录」。**按 §9「10001 排错三步走」的同构思路处理**：

1. **先查 schema**：`tools/list` 取 `knowledge_search` 的 `inputSchema`，核对 `arguments` 每个 key 的拼写与大小写。官方权威字段是 `knowledgeIds`（数组）、`searchMode`（枚举 `vector`/`keyword`/`hybrid`）、`topK`、`minRelevance`、`query`——若写成 `knowledge_ids` / `search_mode` 会直接踩此错
2. **再查必填环境参数**：Personal MCP 业务工具必传 `appId` + `ai_description`；若缺失也可能以「账号未登录」表现，而不是明确的参数错误
3. **最后才考虑 token 权限**：极少见；验证方式——换一个其他业务工具（`get_record_list` 等）看是否正常，如果其他工具都通只有 `knowledge_search` 失败，大概率回到第 1~2 步

**兜底方案**（当确认 `knowledge_search` 对当前 token 彻底不可用时）：明道云知识库本质也是工作表应用，走常规查询：

1. `get_app_worksheets_list(appId)` 找到「知识条目」工作表 ID
2. `get_worksheet_structure(worksheet_id, appId, responseFormat="md")` 查字段（标题字段、标签字段）
3. `get_record_list` + filter 按标题/标签过滤
4. `get_record_details(worksheet_id, appId, row_id)` 拿正文（通常是 **kdocs 外链** 或 **附件**，非纯文本）

> 兜底只是"关键词 / 结构化筛选"，**不等于 RAG 语义检索**。生产级 RAG 场景仍应以 `knowledge_search` 为首选，优先按步骤 1~3 排通。

### 8.15 返回值字段名 ≠ 入参字段名（跨工具传参需转换）

§7.1 已明确 HAP 参数命名 camelCase / snake_case 混用。更隐蔽的坑是：**同一个资源 ID，在列表工具返回值中用驼峰，但作为详情工具的入参时必须改下划线**。直接以返回字段名作为下一个工具的 key 会报 10001。

| 上游工具 | 它返回的字段名 | 作为下游工具入参时要改成 |
|---------|---------------|-------------------------|
| `get_app_worksheets_list` | `worksheetId`（驼峰） | `worksheet_id`（下划线） |
| `get_org_list` | `orgId`（驼峰） | `org_id`（下划线） |
| `get_record_list` | `rowid`（全小写） | `row_id`（下划线） |

```python
# ❌ 错误：直接用返回字段名
ws = get_app_worksheets_list(appId=...)[0]
get_worksheet_structure(worksheetId=ws["worksheetId"], appId=...)  # 10001

# ✅ 正确：取值但改 key
get_worksheet_structure(worksheet_id=ws["worksheetId"], appId=...)
```

**规则**：用上游返回值填下游参数时，**取值不取 key**；key 名准以下游工具的 schema。

---

## 9. 错误码速查

| 错误码 | 含义 | 典型原因 | 解法 |
|--------|------|---------|------|
| `1` | 成功 | — | — |
| `-1` | 通用失败 | 查看 `error_msg` | 按 error_msg 排查 |
| `4` | 权限不足 | 当前身份无该操作权限 | 检查授权类型和用户权限 |
| `10` | 参数错误 | 参数缺失或格式错误 | 检查参数名（驼峰）和值格式 |
| `10001` | HTTP Headers 验证失败 | OAuth token 域名不在白名单 **或 Personal MCP 参数缺失/错误**（如 `get_app_list` 未传 `org_id`） | 确认 token 来源与域名匹配（§8.5）；核参数名与 schema 一致（§7.1 / §8.12） |
| `600101` | 授权已失效 | Bearer token 过期 | 刷新 token |
| `600100` | token 无效/缺失 | token 为空或格式错误 | 检查 Authorization 头 |

### 10001 vs 600101 的区分

| 表现 | 含义 | 路径 |
|------|------|------|
| `10001 Http Headers verification failed` | 域名/scope 层白名单不匹配 | HAP V3 代理层拦截 |
| `600101 授权已失效` / `invalid_token` | token 本身过期或无效 | OAuth introspection 服务拦截 |

> 如果 `tools/list` 能通过但 `tools/call` 返回 10001，有两种可能：
> 1. Personal MCP 调用缺少或错用参数（如 `get_app_list` 传 `appId` 而非 `org_id`，见 §8.12）
> 2. OAuth token 的域名白名单问题（官方 token vs 自建 token，见 §8.5）
>
> 排查顺序：先按 schema 核对参数名，再检查域名白名单。

### 10001 排错三步走（强制顺序）

看到 `10001 Http Headers verification failed` 时，**必须按以下顺序排查**，不要绕过任何一步直接跳到「重新授权 / 重启客户端」结论：

| 顺序 | 检查项 | 依据 | 阅读 |
|------|--------|------|------|
| **1** | 参数名与 schema 是否一致（snake_case vs camelCase；返回值字段名是否被误用为下游入参 key） | 占 10001 场景的大多数 | §7.1 / §8.12 / §8.15 |
| **2** | OAuth token 来源与调用域名是否匹配（官方 token 只能走 `api2.mingdao.com`，自建走 `api.mingdao.com`） | 换过 token 但未换 URL 时常见 | §8.5 |
| **3** | Token / 权限问题 | 极少见，且**权限不足返回 `error_code: 4`，不是 10001** | §5.5 |

**反面例**：`get_app_worksheets_list(appId=...)` 能正常返回工作表，随后 `get_worksheet_structure(worksheetId=..., appId=...)` 报 10001——

- ❌ 错误推导：「token 权限不足，需重新 OAuth」
- ✅ 正确推导：同一 token 同一 appId 上一步刚成功，权限不可能“心跳式丢失”；唯一变量是新加的 `worksheetId` 参数名（应为 `worksheet_id`）——参数名错

---

## 10. 快速决策流程

```
需要访问 HAP 应用数据
│
├─ 是否为明道云官方应用（CRM2025 / 知识库 / ...）？
│   └─ 是 → 只能走 Personal OAuth（§5 + §5.7，因 §8.11）
│           ├─ AI 客户端已集成 MCP → 直接调工具
│           └─ 未集成 → 运行时直调（§5.7 Python / curl 模板）
│
└─ 否 → 是否需要无人值守/定时运行？
    ├─ 是 → 应用级 Appkey+Sign
    │       ├─ AI 直接操作 → MCP（§4.2）
    │       └─ 代码集成 → V3 API（§4.3）
    │
    └─ 否 → 需要受用户权限约束？
        ├─ 是 → 个人级 OAuth Bearer
        │       └─ **强制走 MCP 协议**（§5.2 / §5.6）；调用前先 `tools/list` 看 schema（§7.1）；必传 appId + ai_description（§5.3）
        │
        └─ 否 → 应用级 Appkey+Sign（更简单）
                ├─ AI 直接操作 → MCP（§4.2）
                └─ 代码集成 → V3 API（§4.3）
```

---

## 11. 相关技能

| 技能 | 用途 |
|------|------|
| `hap-mcp-usage` | MCP 配置的自动化安装（9 种 AI 工具平台） |
| `hap-oauth-mcp` | OAuth 授权流程 + Bearer Token 获取/刷新 |
| `hap-v3-api` | V3 REST API 的完整使用规范（Filter、字段类型、批量操作等） |
| `hap-frontend-project` | 使用 HAP 作为后端搭建独立网站 |
| `hap-view-plugin` | 开发 HAP 自定义视图插件 |

---

**技能版本**：v1.5
**适用范围**：明道云 HAP（SaaS / Nocoly / 私有部署）
