#!/usr/bin/env python3
"""
查询盈亏 PnL（reqPnL / reqPnLSingle）

功能：账户级当日/未实现/已实现盈亏；可选逐持仓盈亏。
用法：
    python get_pnl.py                       # 账户级 PnL
    python get_pnl.py --positions           # 账户级 + 逐持仓 PnL
    python get_pnl.py --acc-id DUN512173 --json

字段：dailyPnL(当日) / unrealizedPnL(未实现) / realizedPnL(已实现)。
比 accountSummary 的 ledger 盈亏字段更可靠。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, resolve_account, contract_repr,
    print_result, _fail, _num,
)


def get_pnl(acc_id=None, positions=False, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)
        account = resolve_account(ib, acc_id)

        sub = ib.reqPnL(account)
        ib.sleep(2)
        acct_pnl = {
            "dailyPnL": _num(sub.dailyPnL),
            "unrealizedPnL": _num(sub.unrealizedPnL),
            "realizedPnL": _num(sub.realizedPnL),
        }
        try:
            ib.cancelPnL(account)
        except Exception:
            pass

        pos_pnl = []
        if positions:
            poss = ib.positions(account=account)
            subs = []
            for p in poss:
                c = p.contract
                try:
                    s = ib.reqPnLSingle(account, "", c.conId)
                    subs.append((c, s))
                except Exception:
                    pass
            ib.sleep(2.5)
            for c, s in subs:
                pos_pnl.append({
                    "contract": contract_repr(c),
                    "position": _num(s.position),
                    "dailyPnL": _num(s.dailyPnL),
                    "unrealizedPnL": _num(s.unrealizedPnL),
                    "realizedPnL": _num(s.realizedPnL),
                    "value": _num(s.value),
                })
                try:
                    ib.cancelPnLSingle(account, "", c.conId)
                except Exception:
                    pass

        result = {"account": account, "account_pnl": acct_pnl, "position_pnl": pos_pnl}
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


from common import dash as _f  # 统一的 None->— 占位


def _print_text(result):
    a = result["account_pnl"]
    print("=" * 70)
    print(f"盈亏 PnL  账户: {result['account']}")
    print("=" * 70)
    print(f"  账户级: 今日 {_f(a['dailyPnL'])}   未实现 {_f(a['unrealizedPnL'])}   已实现 {_f(a['realizedPnL'])}")
    if result["position_pnl"]:
        print("\n  逐持仓:")
        print(f"    {'合约':<26} {'数量':>10} {'今日':>12} {'未实现':>12} {'市值':>14}")
        print("    " + "-" * 76)
        for p in result["position_pnl"]:
            print(f"    {str(_f(p['contract'])):<26} {str(_f(p['position'])):>10} "
                  f"{str(_f(p['dailyPnL'])):>12} {str(_f(p['unrealizedPnL'])):>12} {str(_f(p['value'])):>14}")
    print("=" * 70)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="查询盈亏 PnL")
    p.add_argument("--acc-id", default=None, help="账户 ID（多账户时必填）")
    p.add_argument("--positions", action="store_true", help="同时列出逐持仓盈亏")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_pnl(args.acc_id, args.positions, args.output_json)
