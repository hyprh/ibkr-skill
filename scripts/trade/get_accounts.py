#!/usr/bin/env python3
"""
获取账户列表（managedAccounts）

功能：列出当前 Gateway 登录下的所有账户，并标注 paper / live。
用法：
    python get_accounts.py
    python get_accounts.py --json

账户号规则：'DU' 开头 = paper 模拟账户；'U'/其他 = live 实盘账户。
连接的端口决定环境（4002=paper Gateway，4001=live Gateway）。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, is_live_account, get_config,
    print_result, _fail,
)


def get_accounts(output_json=False):
    ib = None
    try:
        cfg = get_config()
        ib = connect(readonly=True)
        accounts = [a for a in ib.managedAccounts() if a]
        records = [{
            "acc_id": a,
            "type": "live" if is_live_account(a) else "paper",
        } for a in accounts]
        result = {
            "host": cfg.host, "port": cfg.port,
            "env": "live (4001/7496?)" if cfg.port in (4001, 7496) else "paper (4002/7497?)",
            "accounts": records,
        }
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 60)
    print(f"账户列表  连接: {result['host']}:{result['port']}  ({result['env']})")
    print("=" * 60)
    for r in result["accounts"]:
        flag = "⚠️ 实盘" if r["type"] == "live" else "模拟"
        print(f"  {r['acc_id']}   [{flag}]")
    print("=" * 60)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="获取账户列表")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_accounts(args.output_json)
