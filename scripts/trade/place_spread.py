#!/usr/bin/env python3
"""
垂直价差下单（借方价差 / 多腿 combo）—— 定义风险,最大亏损=净支出(硬止损)

功能：用两腿期权组合下"借方垂直价差",最大亏损在开仓即锁定(=净支出×100×张数),
      跳空也打不穿。支持牛市看涨价差 / 熊市看跌价差。
用法：
    # 牛市看涨价差: 买低行权 call + 卖高行权 call, 净支出 2.50
    python place_spread.py --code BABA --type BULL_CALL --expiry 20260717 \
        --buy-strike 113 --sell-strike 118 --price 2.50 --quantity 1
    # 熊市看跌价差: 买高行权 put + 卖低行权 put
    python place_spread.py --code BABA --type BEAR_PUT --expiry 20260717 \
        --buy-strike 113 --sell-strike 108 --price 2.20 --quantity 1
    # 下单前预览保证金/佣金(whatIf,不下单)
    python place_spread.py ... --preview

参数：
- --type      : BULL_CALL(买低卖高 call) / BEAR_PUT(买高卖低 put) —— 均为借方,定义风险
- --buy-strike / --sell-strike : 买入腿 / 卖出腿 的行权价
- --price     : 净支出限价(每份价差,如 2.50 = 每份 $250)
- --quantity  : 价差份数
- --preview   : whatIf 预览(保证金/佣金),不下单
- --confirmed : 实盘下单确认(实盘环境硬约束)

风险:  最大亏损 = 净支出 × 100 × 份数(硬止损);最大盈利 = (行权价差 − 净支出) × 100 × 份数。
约束:  当前仅支持单标的、同到期日、1:1 比例的两腿借方垂直价差。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, qualify, resolve_account, is_live_env,
    require_live_confirmation, contract_repr, attach_error_collector,
    audit_log, json_dumps, _fail, _num,
    Option, Contract, LimitOrder, REJECTED_STATUSES, WORKING_STATUSES,
)
from ib_async import ComboLeg

# 借方垂直价差: (右, 买入腿应低/高于卖出腿)
_SPREAD = {
    "BULL_CALL": {"right": "C", "desc": "牛市看涨价差(买低行权call+卖高行权call)"},
    "BEAR_PUT": {"right": "P", "desc": "熊市看跌价差(买高行权put+卖低行权put)"},
}


def place_spread(code, spread_type, expiry, buy_strike, sell_strike, price, quantity,
                 acc_id=None, confirmed=False, preview=False, output_json=False):
    spread_type = spread_type.upper()
    if spread_type not in _SPREAD:
        _fail(f"--type 仅支持 {list(_SPREAD)}", output_json)
    if quantity is None or quantity <= 0:
        _fail("份数必须为正整数", output_json)
    right = _SPREAD[spread_type]["right"]
    # 方向校验:牛市看涨买低卖高;熊市看跌买高卖低
    if spread_type == "BULL_CALL" and not buy_strike < sell_strike:
        _fail("BULL_CALL 需 买入行权价 < 卖出行权价", output_json)
    if spread_type == "BEAR_PUT" and not buy_strike > sell_strike:
        _fail("BEAR_PUT 需 买入行权价 > 卖出行权价", output_json)

    ib = None
    try:
        ib = connect(readonly=False)
        errors = attach_error_collector(ib)
        account = resolve_account(ib, acc_id)
        sym = code.split(".")[-1].upper()  # 去掉可能的 US. 前缀
        cur = "USD"

        # qualify 两腿
        buy_leg = qualify(ib, Option(sym, expiry, buy_strike, right, "SMART", currency=cur), output_json)
        sell_leg = qualify(ib, Option(sym, expiry, sell_strike, right, "SMART", currency=cur), output_json)

        # 组装 BAG 组合合约
        bag = Contract(symbol=sym, secType="BAG", exchange="SMART", currency=cur)
        bag.comboLegs = [
            ComboLeg(conId=buy_leg.conId, ratio=1, action="BUY", exchange="SMART"),
            ComboLeg(conId=sell_leg.conId, ratio=1, action="SELL", exchange="SMART"),
        ]

        width = abs(sell_strike - buy_strike)
        max_loss = round(price * 100 * quantity, 2)          # 净支出 = 硬止损
        max_gain = round((width - price) * 100 * quantity, 2)
        summary = {
            "type": spread_type, "desc": _SPREAD[spread_type]["desc"],
            "underlying": sym, "expiry": expiry,
            "buy_strike": buy_strike, "sell_strike": sell_strike, "right": right,
            "net_debit": price, "quantity": quantity,
            "max_loss": max_loss, "max_gain": max_gain,
            "account": account, "env": "live" if is_live_env(account) else "paper",
        }

        # 限价单:借方价差 = BUY 组合 @ 净支出
        order = LimitOrder("BUY", quantity, float(price))
        order.account = account

        # whatIf 预览
        if preview:
            st = ib.whatIfOrder(bag, order)
            summary["preview"] = {
                "init_margin_change": _num(getattr(st, "initMarginChange", None)),
                "maint_margin_change": _num(getattr(st, "maintMarginChange", None)),
                "commission": _num(getattr(st, "commission", None)),
                "warning": getattr(st, "warningText", None) or None,
            }
            if output_json:
                print(json_dumps({"action": "spread_preview", **summary}))
            else:
                _print_summary(summary, "价差预览(whatIf,未下单)")
                pv = summary["preview"]
                print(f"  初始保证金变动: {pv['init_margin_change']}  预估佣金: {pv['commission']}")
                if pv["warning"]:
                    print(f"  ⚠️ {pv['warning']}")
                print("=" * 64)
            return

        # 实盘安全门
        require_live_confirmation(
            account, confirmed, "价差下单",
            [f"{summary['desc']}", f"{sym} {expiry}  买{buy_strike}/卖{sell_strike} {right}",
             f"净支出: {price}/份  份数: {quantity}",
             f"最大亏损(硬止损): ${max_loss}   最大盈利: ${max_gain}"],
            output_json,
        )

        trade = ib.placeOrder(bag, order)
        ib.sleep(2)
        status = trade.orderStatus.status
        order_id = trade.order.orderId

        blocking = [e for e in errors if e["code"] in (321, 201)]
        if blocking or status in REJECTED_STATUSES:
            hint = "; ".join(e.get("hint") or e["msg"] for e in blocking) or f"状态 {status}"
            audit_log({"action": "place_spread", "result": "rejected", **summary, "error": hint})
            _fail(f"价差下单未成功(状态 {status or 'N/A'}): {hint}", output_json)

        result_state = "submitted" if status in WORKING_STATUSES else "pending_unknown"
        result = {"order_id": order_id, "status": status or "unknown", "result": result_state, **summary}
        audit_log({"action": "place_spread", **result})

        if output_json:
            print(json_dumps(result))
        else:
            _print_summary(summary, "价差已提交" if result_state == "submitted" else "价差状态未确认(用 get_orders.py 复查)")
            print(f"  订单ID: {order_id}  状态: {status or 'unknown'}")
            print("=" * 64)
            for w in errors:
                print(f"  [提示 {w['code']}] {w.get('hint') or w['msg']}")
    except SystemExit:
        raise
    except Exception as e:
        if _os.getenv("IBKR_DEBUG"):
            import traceback
            traceback.print_exc()
        audit_log({"action": "place_spread", "result": "error", "code": code,
                   "type": spread_type, "error": str(e)})
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_summary(s, title):
    print("=" * 64)
    print(title)
    print("=" * 64)
    print(f"  {s['desc']}")
    print(f"  {s['underlying']} {s['expiry']}  买 {s['buy_strike']} / 卖 {s['sell_strike']} {s['right']}")
    print(f"  净支出: {s['net_debit']}/份  份数: {s['quantity']}  账户: {s['account']} ({s['env']})")
    print(f"  ★ 最大亏损(硬止损): ${s['max_loss']}   最大盈利: ${s['max_gain']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="垂直价差下单(借方,定义风险)")
    p.add_argument("--code", required=True, help="正股代码,如 BABA / QQQ")
    p.add_argument("--type", required=True, choices=list(_SPREAD), help="价差类型")
    p.add_argument("--expiry", required=True, help="到期日 YYYYMMDD")
    p.add_argument("--buy-strike", type=float, required=True, help="买入腿行权价")
    p.add_argument("--sell-strike", type=float, required=True, help="卖出腿行权价")
    p.add_argument("--price", type=float, required=True, help="净支出限价(每份)")
    p.add_argument("--quantity", type=int, required=True, help="份数")
    p.add_argument("--acc-id", default=None, help="账户 ID(多账户必填)")
    p.add_argument("--preview", action="store_true", help="whatIf 预览,不下单")
    p.add_argument("--confirmed", action="store_true", help="实盘下单确认")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON")
    args = p.parse_args()
    place_spread(args.code, args.type, args.expiry, args.buy_strike, args.sell_strike,
                 args.price, args.quantity, args.acc_id, args.confirmed, args.preview,
                 args.output_json)
