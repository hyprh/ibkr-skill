#!/usr/bin/env python3
"""
下单（placeOrder）

功能：在指定账户买入/卖出。默认连接 paper Gateway（端口 4002）。
用法：
    # 限价单（默认）
    python place_order.py --code AAPL --side BUY --quantity 10 --price 150
    # 市价单
    python place_order.py --code AAPL --side BUY --quantity 10 --order-type MKT
    # 止损单
    python place_order.py --code AAPL --side SELL --quantity 10 --order-type STP --aux-price 140
    # 下单前预览保证金/佣金影响（不下单，whatIf）
    python place_order.py --code AAPL --side BUY --quantity 10 --price 150 --preview
    # 实盘下单（需 --confirmed，且账户为 U 开头）
    python place_order.py --code AAPL --side BUY --quantity 1 --price 150 --confirmed

安全约束（代码硬约束）：
- 实盘环境（账户号非 DU 开头，或连接的是 live 端口 4001/7496）下单**必须**带 --confirmed，否则只打印预览并退出(code 2)。
- 若 Gateway 处于 Read-Only API 只读模式，下单会被拒绝（错误 321），脚本会给出明确提示。

参数：
- --order-type : LMT(限价,默认) / MKT(市价) / STP(止损)
- --tif        : DAY(默认) / GTC / IOC / OPG
- --aux-price  : 止损价（STP 必填）
- --outside-rth: 允许盘前盘后成交（仅限价单）
- --preview    : whatIf 预览，返回保证金占用/预估佣金/对净值影响，不真正下单
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify, resolve_account,
    is_live_env, require_live_confirmation, contract_repr,
    attach_error_collector, audit_log, json_dumps, _fail, _num,
    WORKING_STATUSES, REJECTED_STATUSES,
    LimitOrder, MarketOrder, StopOrder,
)


def _build_order(side, quantity, order_type, price, aux_price, tif, outside_rth, account):
    ot = order_type.upper()
    action = side.upper()
    if ot == "MKT":
        o = MarketOrder(action, quantity)
    elif ot == "STP":
        if aux_price is None:
            _fail("止损单(STP) 必须指定 --aux-price 止损价")
        o = StopOrder(action, quantity, aux_price)
    else:  # LMT
        if price is None:
            _fail("限价单(LMT) 必须指定 --price")
        o = LimitOrder(action, quantity, price)
    o.tif = tif.upper()
    o.account = account
    if outside_rth:
        o.outsideRth = True
    return o


def _wait_for_status(ib, trade, deadline=8.0):
    """事件驱动等待：轮询到订单离开 transient 状态或截止。返回最终 orderStatus。"""
    import time
    end = time.time() + deadline
    # ValidationError 是 ib_async 在收到下单警告(如 399 休市不下达)时的瞬态
    transient = {"", "PendingSubmit", "ApiPending", "ValidationError"}
    while time.time() < end:
        ib.waitOnUpdate(timeout=0.5)
        st = trade.orderStatus.status
        if st not in transient:
            if st in ("Filled", "Cancelled", "ApiCancelled", "Inactive"):
                break
            ib.waitOnUpdate(timeout=0.3)
            break
    # 若仍是瞬态（常见于休市的 399 持单），主动全量同步一次拿权威状态（会收敛到 PreSubmitted）
    if trade.orderStatus.status in transient:
        try:
            ib.reqAllOpenOrders()
            ib.sleep(0.5)
        except Exception:
            pass
    return trade.orderStatus


def place_order(code, side, quantity, price=None, order_type="LMT", aux_price=None,
                tif="DAY", acc_id=None, confirmed=False, outside_rth=False,
                preview=False, output_json=False):
    if quantity is None or quantity <= 0:
        _fail("数量必须为正整数", output_json)

    ib = None
    try:
        ib = connect(readonly=False)  # 下单必须非只读
        errors = attach_error_collector(ib)
        account = resolve_account(ib, acc_id)
        contract = parse_contract(code)
        qc = qualify(ib, contract, output_json)

        summary = {
            "account": account, "env": "live" if is_live_env(account) else "paper",
            "contract": contract_repr(qc), "side": side.upper(), "quantity": quantity,
            "order_type": order_type.upper(), "price": price, "aux_price": aux_price, "tif": tif.upper(),
        }
        order = _build_order(side, quantity, order_type, price, aux_price, tif, outside_rth, account)

        # whatIf 预览：返回保证金/佣金影响，不下单
        if preview:
            state = ib.whatIfOrder(qc, order)
            pv = {
                "preview": True, **summary,
                "init_margin_change": _num(getattr(state, "initMarginChange", None)),
                "maint_margin_change": _num(getattr(state, "maintMarginChange", None)),
                "equity_with_loan_change": _num(getattr(state, "equityWithLoanChange", None)),
                "commission": _num(getattr(state, "commission", None)),
                "commission_currency": getattr(state, "commissionCurrency", None),
                "warning": getattr(state, "warningText", None) or None,
            }
            if output_json:
                print(json_dumps(pv))
            else:
                print("=" * 60); print("下单预览（whatIf，未下单）"); print("=" * 60)
                print(f"  合约    : {summary['contract']}  {summary['side']} {quantity} @ {summary['order_type']}")
                print(f"  初始保证金变动 : {pv['init_margin_change']}")
                print(f"  维持保证金变动 : {pv['maint_margin_change']}")
                print(f"  净值影响       : {pv['equity_with_loan_change']}")
                print(f"  预估佣金       : {pv['commission']} {pv['commission_currency'] or ''}")
                if pv["warning"]:
                    print(f"  ⚠️ 警告        : {pv['warning']}")
                print("=" * 60)
            return

        # 实盘硬约束：必须 --confirmed（账户或端口判定为实盘）
        require_live_confirmation(
            account, confirmed, "下单",
            [f"合约: {summary['contract']}", f"方向: {summary['side']}", f"数量: {quantity}",
             f"类型: {summary['order_type']}", f"价格: {price}", f"止损价: {aux_price}", f"TIF: {summary['tif']}"],
            output_json,
        )

        trade = ib.placeOrder(qc, order)
        ost = _wait_for_status(ib, trade)
        status = ost.status
        order_id = trade.order.orderId
        filled = _num(ost.filled)
        remaining = _num(ost.remaining)

        # 拒单判定：任何 blocking 错误 => 拒绝；或状态进入拒绝态；解耦了状态白名单
        blocking = [e for e in errors if e["code"] in (321, 201)]
        rejected = bool(blocking) or status in REJECTED_STATUSES
        if rejected:
            hint = "; ".join(e.get("hint") or e["msg"] for e in blocking) or f"状态 {status}"
            audit_log({"action": "place_order", "result": "rejected", **summary,
                       "status": status, "error": hint})
            _fail(f"下单未成功（状态 {status or 'N/A'}）：{hint}", output_json)

        # 非工作态且无错误：状态未知，不谎报 submitted
        result_state = "submitted" if status in WORKING_STATUSES else "pending_unknown"
        result = {"order_id": order_id, "status": status or "unknown",
                  "filled": filled, "remaining": remaining, "result": result_state, **summary}
        audit_log({"action": "place_order", **result})

        if output_json:
            print(json_dumps(result))
        else:
            header = "下单已提交" if result_state == "submitted" else "下单状态未确认（请用 get_orders.py 复查）"
            print("=" * 60); print(header); print("=" * 60)
            print(f"  订单 ID : {order_id}")
            print(f"  状态    : {status or 'unknown'}   已成交: {filled}  剩余: {remaining}")
            print(f"  账户    : {account} ({summary['env']})")
            print(f"  合约    : {summary['contract']}")
            _pxline = (f"  价格: {price}" if summary["order_type"] == "LMT"
                       else (f"  止损价: {aux_price}" if summary["order_type"] == "STP" else "  市价"))
            print(f"  方向    : {summary['side']}  数量: {quantity}  类型: {summary['order_type']}"
                  f"{_pxline}  TIF: {summary['tif']}")
            print("=" * 60)
            for w in errors:
                print(f"  [提示 {w['code']}] {w.get('hint') or w['msg']}")
    except SystemExit:
        raise
    except Exception as e:
        audit_log({"action": "place_order", "result": "error", "code": code,
                   "side": side, "quantity": quantity, "error": str(e)})
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="下单")
    p.add_argument("--code", required=True, help="标的代码，如 AAPL / HK.700")
    p.add_argument("--side", required=True, choices=["BUY", "SELL"], help="方向")
    p.add_argument("--quantity", type=float, required=True, help="数量")
    p.add_argument("--price", type=float, default=None, help="价格（限价单必填）")
    p.add_argument("--order-type", default="LMT", choices=["LMT", "MKT", "STP"], help="订单类型")
    p.add_argument("--aux-price", type=float, default=None, help="止损价（STP 必填）")
    p.add_argument("--tif", default="DAY", choices=["DAY", "GTC", "IOC", "OPG"], help="有效期")
    p.add_argument("--acc-id", default=None, help="账户 ID（多账户时必填）")
    p.add_argument("--outside-rth", action="store_true", help="允许盘前盘后成交")
    p.add_argument("--preview", action="store_true", help="whatIf 预览（保证金/佣金），不下单")
    p.add_argument("--confirmed", action="store_true", help="实盘下单确认标志")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    place_order(code=args.code, side=args.side, quantity=args.quantity, price=args.price,
                order_type=args.order_type, aux_price=args.aux_price, tif=args.tif,
                acc_id=args.acc_id, confirmed=args.confirmed, outside_rth=args.outside_rth,
                preview=args.preview, output_json=args.output_json)
