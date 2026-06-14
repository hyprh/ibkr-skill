#!/usr/bin/env python3
"""
全账户持仓与资金（不过滤账户）

功能：一次性列出当前登录下**所有账户**的净值与持仓，适合多账户/子账户场景。
用法：
    python get_all_portfolios.py
    python get_all_portfolios.py --json

单账户登录时等价于 get_portfolio.py，但无需指定 --acc-id。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, contract_repr, is_live_account,
    print_result, _fail, _num,
)

_FUND_TAGS = {"NetLiquidation", "TotalCashValue", "AvailableFunds", "BuyingPower"}


def get_all_portfolios(output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)
        accounts = [a for a in ib.managedAccounts() if a]

        # 资金：accountSummary() 无参返回所有账户（不预先限制为 managedAccounts）
        funds = {}
        for v in ib.accountSummary():
            if v.tag in _FUND_TAGS:
                funds.setdefault(v.account, {})
                funds[v.account].setdefault(v.tag, {"value": _num(v.value), "currency": v.currency})

        # 持仓：positions() 无参返回所有账户
        pos_by_acc = {}
        for p in ib.positions():
            acc = p.account
            pos_by_acc.setdefault(acc, [])
            c = p.contract
            pos_by_acc[acc].append({
                "contract": contract_repr(c),
                "position": _num(p.position),
                "avgCost": _num(p.avgCost),
            })

        # 账户集合 = managedAccounts ∪ 持仓/资金里出现的账户（FA 子账户可能不在 managedAccounts）
        all_accts = list(dict.fromkeys(accounts + list(funds.keys()) + list(pos_by_acc.keys())))
        out = []
        for a in all_accts:
            out.append({
                "account": a,
                "type": "live" if is_live_account(a) else "paper",
                "funds": funds.get(a, {}),
                "positions": pos_by_acc.get(a, []),
            })
        result = {"account_count": len(all_accts), "accounts": out}
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


from common import dash as _f  # 统一的 None->— 占位


def _print_text(result):
    print("=" * 74)
    print(f"全账户持仓与资金  共 {result['account_count']} 个账户")
    print("=" * 74)
    for acc in result["accounts"]:
        f = acc["funds"]

        def _c(tag):
            d = f.get(tag)
            return f"{_f(d['value'])} {d['currency']}" if d else "—"

        flag = "⚠️实盘" if acc["type"] == "live" else "模拟"
        print(f"\n  ▌账户 {acc['account']} [{flag}]")
        print(f"    净值: {_c('NetLiquidation')}   现金: {_c('TotalCashValue')}"
              f"   购买力: {_c('BuyingPower')}")
        if not acc["positions"]:
            print("    持仓: （无）")
        else:
            print("    持仓:")
            for p in acc["positions"]:
                print(f"      {str(_f(p['contract'])):<26} {str(_f(p['position'])):>10} @ {_f(p['avgCost'])}")
    print("\n" + "=" * 74)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="全账户持仓与资金")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_all_portfolios(args.output_json)
