"""hap-access: HAP 应用通用访问 CLI。

面向业务 skill 的单一调用入口。三种 mode 的传输层 + profile 存储 + 凭据加载
全部封装在这里，业务 skill 只需：

    hap-access call --profile=<name> --tool=<name> --args='{...}'

子模块：
  - profile.py     : Profile 加载 / schema / 权限检查
  - mcp_client.py  : personal_mcp + app_mcp 共用 JSON-RPC 客户端
  - api_client.py  : v3_api REST 客户端
  - cli.py         : argparse 入口
"""

__version__ = "0.3.0"
