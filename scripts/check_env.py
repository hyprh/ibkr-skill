#!/usr/bin/env python3
"""
环境自检：ib_async 安装情况 + Gateway 连通性 + 账户 + 行情类型

用法：
    python check_env.py
    python check_env.py --json
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from common import connect, safe_disconnect, get_config, is_live_account, json_dumps


def check_env(output_json=False):
    cfg = get_config()
    info = {
        "host": cfg.host, "port": cfg.port,
        "market_data_type": cfg.market_data_type,
        "default_client_id_env": cfg.client_id,
    }
    try:
        import ib_async
        info["ib_async_version"] = ib_async.__version__
    except ImportError:
        info["ib_async_version"] = None

    ib = None
    try:
        ib = connect(readonly=True)
        info["connected"] = True
        info["server_version"] = ib.client.serverVersion()
        accs = [a for a in ib.managedAccounts() if a]
        info["accounts"] = [{"acc_id": a, "type": "live" if is_live_account(a) else "paper"} for a in accs]
    except SystemExit:
        info["connected"] = False
    except Exception as e:
        info["connected"] = False
        info["error"] = str(e)
    finally:
        safe_disconnect(ib)

    if output_json:
        print(json_dumps(info))
    else:
        print("=" * 56)
        print("IBKR 环境自检")
        print("=" * 56)
        print(f"  ib_async 版本 : {info.get('ib_async_version')}")
        print(f"  Gateway       : {info['host']}:{info['port']}")
        print(f"  连接状态      : {'✅ 已连接' if info.get('connected') else '❌ 未连接'}")
        if info.get("server_version"):
            print(f"  服务器版本    : {info['server_version']}")
        print(f"  行情类型      : {info['market_data_type']} (1实时/2冻结/3延迟/4延迟冻结)")
        for a in info.get("accounts", []):
            flag = "⚠️ 实盘" if a["type"] == "live" else "模拟"
            print(f"  账户          : {a['acc_id']} [{flag}]")
        if info.get("error"):
            print(f"  错误          : {info['error']}")
        print("=" * 56)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="IBKR 环境自检")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    check_env(args.output_json)
