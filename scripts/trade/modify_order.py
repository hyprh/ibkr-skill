#!/usr/bin/env python3
"""
改单（修改价格/数量/止损价后用相同 orderId 重新 placeOrder）

功能：修改已挂订单。IBKR 的改单方式是用相同 orderId 再次 placeOrder。
用法：
    python modify_order.py --order-id 12 --price 155            # 改限价
    python modify_order.py --order-id 12 --quantity 20          # 改数量
    python modify_order.py --order-id 12 --aux-price 140        # 改止损触发价(STP)
    python modify_order.py --order-id 12 --price 155 --confirmed   # 实盘需 --confirmed

参数：
- --price     : 新限价（LMT 用 lmtPrice；纯 STP 单会作为触发价）
- --aux-price : 新止损触发价（STP / STP LMT 的 auxPrice）
- --quantity  : 新总数量（非增量）
- --confirmed : 实盘改单确认标志
- 至少提供 --price / --aux-price / --quantity 之一；未提供的字段保持原值。

约束：
- 只能改**本连接（同一 clientId）下的单**。其它 client/TWS 手工单无法改（会提示），
  否则 IBKR 会把它当成全新订单误下。用下单时的 clientId（设 IB_CLIENT_ID）或在 GUI 改。
- 实盘环境改单必须 --confirmed。
- 未给 order-id 时先用 get_orders.py 查询。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, contract_repr, attach_error_collector,
    require_live_confirmation, audit_log, json_dumps, _fail, _num,
    REJECTED_STATUSES,
)


def modify_order(order_id, price=None, quantity=None, aux_price=None,
                 confirmed=False, output_json=False):
    if price is None and quantity is None and aux_price is None:
        _fail("请至少提供 --price / --aux-price / --quantity 之一", output_json)

    ib = None
    try:
        ib = connect(readonly=False)
        errors = attach_error_collector(ib)
        ib.reqAllOpenOrders()  # 先全量发现，再校验归属

        my_cid = ib.client.clientId
        candidates = [t for t in ib.openTrades() if t.order.orderId == order_id]
        target = next((t for t in candidates if t.order.clientId in (my_cid, 0)), None)
        if target is None:
            if candidates:
                other = candidates[0].order.clientId
                _fail(f"订单 {order_id} 由其它 client(clientId={other})/手工下单，本连接(clientId={my_cid}) "
                      f"无法改单（否则会被当成新订单误下）。请用下单时的 clientId（设 IB_CLIENT_ID={other}）或在 Gateway GUI 修改。",
                      output_json)
            _fail(f"未找到 orderId={order_id} 的挂单（可能已成交/已撤销）。用 get_orders.py 查询。",
                  output_json)

        order = target.order
        account = order.account
        otype = (order.orderType or "").upper()
        is_stop = otype == "STP"

        old = {"lmt_price": _num(order.lmtPrice) or None,
               "aux_price": _num(order.auxPrice) or None,
               "quantity": _num(order.totalQuantity)}

        # 实盘安全门
        require_live_confirmation(
            account, confirmed, "改单",
            [f"订单: {order_id}", f"合约: {contract_repr(target.contract)}", f"类型: {otype}",
             f"价格: {old['lmt_price']} -> {price if price is not None else '不变'}",
             f"止损价: {old['aux_price']} -> {aux_price if aux_price is not None else '不变'}",
             f"数量: {old['quantity']} -> {quantity if quantity is not None else '不变'}"],
            output_json,
        )

        if quantity is not None:
            order.totalQuantity = quantity
        if is_stop:
            # 纯止损单触发价在 auxPrice；--price 或 --aux-price 都视为触发价
            trig = aux_price if aux_price is not None else price
            if trig is not None:
                order.auxPrice = trig
        else:
            if price is not None:
                order.lmtPrice = price
            if aux_price is not None:   # STP LMT 的触发腿
                order.auxPrice = aux_price

        trade = ib.placeOrder(target.contract, order)  # 同 orderId 重新提交即为修改
        ib.sleep(1.5)
        status = trade.orderStatus.status

        new = {"lmt_price": _num(order.lmtPrice) or None,
               "aux_price": _num(order.auxPrice) or None,
               "quantity": _num(order.totalQuantity)}
        result = {"order_id": order_id, "contract": contract_repr(target.contract),
                  "order_type": otype, "old": old, "new": new, "status": status}

        blocking = [e for e in errors if e["code"] in (321, 201)]
        if blocking or status in REJECTED_STATUSES:
            hint = "; ".join(e.get("hint") or e["msg"] for e in blocking) or f"状态 {status}"
            audit_log({"action": "modify_order", "result": "rejected", **result, "error": hint})
            _fail(f"改单未成功（状态 {status or 'N/A'}）：{hint}", output_json)
        audit_log({"action": "modify_order", "result": "submitted", **result})

        if output_json:
            print(json_dumps(result))
        else:
            print("=" * 56); print("改单已提交"); print("=" * 56)
            print(f"  订单 ID : {order_id}   类型: {otype}   状态: {status}")
            print(f"  合约    : {result['contract']}")
            print(f"  限价    : {old['lmt_price']} -> {new['lmt_price']}")
            print(f"  止损价  : {old['aux_price']} -> {new['aux_price']}")
            print(f"  数量    : {old['quantity']} -> {new['quantity']}")
            print("=" * 56)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="改单")
    p.add_argument("--order-id", type=int, required=True, help="订单 ID")
    p.add_argument("--price", type=float, default=None, help="新限价")
    p.add_argument("--aux-price", type=float, default=None, help="新止损触发价（STP）")
    p.add_argument("--quantity", type=float, default=None, help="新总数量")
    p.add_argument("--confirmed", action="store_true", help="实盘改单确认标志")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    modify_order(args.order_id, args.price, args.quantity, args.aux_price,
                 args.confirmed, args.output_json)
