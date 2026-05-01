# hap-app-access

明道云 HAP 应用**通用访问技能**，覆盖两种授权类型（应用级 Appkey+Sign / 个人级 OAuth Bearer）与两种调用路径（MCP 协议 / V3 REST API）的交叉组合。

不包含任何具体业务逻辑，只提供通用的授权、连接、调用方法论与陷阱清单。

## 安装

```bash
# 方式一：克隆到 Qoder 技能目录
cd ~/.qoder/skills
git clone https://github.com/topmachinegun/hap-app-access.git

# 方式二：手动放置
mkdir -p ~/.qoder/skills/hap-app-access
curl -o ~/.qoder/skills/hap-app-access/SKILL.md https://raw.githubusercontent.com/topmachinegun/hap-app-access/main/SKILL.md
```

安装后 Qoder 自动识别技能，无需额外配置。

## 技能结构

| 章节 | 内容 |
|------|------|
| §1 授权类型总览 | Appkey+Sign vs OAuth Bearer 对比与选择 |
| §2 两种调用路径 | MCP 协议 vs V3 REST API 对比与选择 |
| §3 交叉矩阵 | 2×2 四种组合的可行性 |
| §4 应用级授权 | 凭证获取 + MCP/V3 API 配置 |
| §5 个人级授权 | Token 获取 + MCP 配置 + 过期刷新 + 限制说明 |
| §6 API Host | 明道云/Nocoly/私有部署域名 |
| §7 通用调用规范 | 驼峰命名、Filter、分页、字段 ID |
| §8 通用陷阱清单 | 10 个高频坑与解法 |
| §9 错误码速查 | 10001 vs 600101 区分 |
| §10 快速决策流程 | 选型决策树 |
| §11 相关技能 | 5 个关联技能索引 |

## 与其他 HAP 技能的关系

| 技能 | 定位 |
|------|------|
| **hap-app-access**（本技能） | 上层方法论：选授权、选路径、避坑 |
| hap-mcp-usage | MCP 配置安装（9 种 AI 工具平台） |
| hap-oauth-mcp | OAuth 授权流程 + Bearer Token 获取/刷新 |
| hap-v3-api | V3 REST API 完整规范（Filter、字段类型、批量操作） |
| hap-frontend-project | HAP 作为后端搭建独立网站 |
| hap-view-plugin | HAP 自定义视图插件开发 |

## License

MIT
