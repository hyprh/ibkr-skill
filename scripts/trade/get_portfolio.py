#!/usr/bin/env python3
"""
获取持仓与资金（positions + accountSummary + PnL）

功能：列出指定账户的持仓明细、关键资金指标、以及账户级盈亏。
用法：
    python get_portfolio.py
    python get_portfolio.py --acc-id DUN512173
    python get_portfolio.py --json

资金字段（来自 accountSummary，均为账户基础货币）：
- NetLiquidation   净清算价值（账户净值）
- TotalCashValue   现金
- AvailableFunds   可用资金
- BuyingPower      购买力
- GrossPositionValue 持仓总市值
盈亏字段（来自 reqPnL，比 accountSummary 的 ledger 字段可靠）：
- dailyPnL / unrealizedPnL / realizedPnL
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, resolve_account, contract_repr,
    print_result, _fail, _num,
)

# 这些都是 accountSummary 的显式 tag，按基础货币返回（PnL 不在其中，单独用 reqPnL）
_CASH_TAGS = {
    "NetLiquidation", "TotalCashValue", "AvailableFunds", "BuyingPower",
    "GrossPositionValue",
}


def _fmt(v):
    return "—" if v is None else v


def get_portfolio(acc_id=None, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)
        account = resolve_account(ib, acc_id)

        # 持仓
        positions = []
        for p in ib.positions(account=account):
            c = p.contract
            positions.append({
                "symbol": c.symbol,
                "secType": c.secType,
                "exchange": c.exchange or c.primaryExchange,
                "currency": c.currency,
                "contract": contract_repr(c),
                "position": _num(p.position),
                "avgCost": _num(p.avgCost),
            })

        # 资金（accountSummary 这些 tag 已是基础货币、每个仅一行）
        cash = {}
        for v in ib.accountSummary(account):
            if v.account == account and v.tag in _CASH_TAGS and v.tag not in cash:
                cash[v.tag] = {"value": _num(v.value), "currency": v.currency}

        # 账户级盈亏：reqPnL 比 accountSummary 的 ledger PnL 可靠
        pnl = {"dailyPnL": None, "unrealizedPnL": None, "realizedPnL": None}
        try:
            sub = ib.reqPnL(account)
            ib.sleep(1.5)
            pnl = {"dailyPnL": _num(sub.dailyPnL), "unrealizedPnL": _num(sub.unrealizedPnL),
                   "realizedPnL": _num(sub.realizedPnL)}
            ib.cancelPnL(account)
        except Exception:
            pass

        result = {"account": account, "positions": positions, "cash": cash, "pnl": pnl}
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 74)
    print(f"持仓与资金  账户: {result['account']}")
    print("=" * 74)
    cash = result["cash"]
    pnl = result.get("pnl", {})

    def _c(tag):
        d = cash.get(tag)
        return f"{_fmt(d['value'])} {d['currency']}" if d else "—"

    print("  资金概览:")
    print(f"    净值(NetLiq): {_c('NetLiquidation')}    现金: {_c('TotalCashValue')}")
    print(f"    可用资金: {_c('AvailableFunds')}    购买力: {_c('BuyingPower')}")
    print(f"    持仓市值: {_c('GrossPositionValue')}")
    print(f"    盈亏: 今日 {_fmt(pnl.get('dailyPnL'))}  未实现 {_fmt(pnl.get('unrealizedPnL'))}"
          f"  已实现 {_fmt(pnl.get('realizedPnL'))}")
    print("\n  持仓:")
    if not result["positions"]:
        print("    （无持仓）")
    else:
        print(f"    {'合约':<28} {'数量':>12} {'均价':>14}")
        print("    " + "-" * 56)
        for p in result["positions"]:
            print(f"    {str(_fmt(p['contract'])):<28} {str(_fmt(p['position'])):>12} "
                  f"{str(_fmt(p['avgCost'])):>14}")
    print("=" * 74)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="获取持仓与资金")
    p.add_argument("--acc-id", default=None, help="账户 ID（多账户时必填）")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_portfolio(args.acc_id, args.output_json)
