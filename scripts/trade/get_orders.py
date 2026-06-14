#!/usr/bin/env python3
"""
查询当前未完成订单（reqOpenOrders / openTrades）

功能：列出账户当前所有挂单（未成交/部分成交）。
用法：
    python get_orders.py
    python get_orders.py --acc-id DUN512173
    python get_orders.py --json
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, resolve_account, contract_repr,
    print_result, _fail, _num,
)


def get_orders(acc_id=None, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)  # 纯查询；reqAllOpenOrders 在只读连接下同样可用
        account = resolve_account(ib, acc_id)
        ib.reqAllOpenOrders()  # 阻塞调用，返回时 openTrades() 已就绪（含所有 client/TWS 手工单）

        records = []
        for t in ib.openTrades():
            o, c, st = t.order, t.contract, t.orderStatus
            if account and o.account != account:
                continue
            records.append({
                "order_id": o.orderId,
                "perm_id": o.permId,
                "contract": contract_repr(c),
                "action": o.action,
                "order_type": o.orderType,
                "quantity": _num(o.totalQuantity),
                "price": _num(o.lmtPrice) or None,
                "aux_price": _num(o.auxPrice) or None,
                "tif": o.tif,
                "status": st.status,
                "filled": _num(st.filled),
                "remaining": _num(st.remaining),
            })
        result = {"account": account, "count": len(records), "orders": records}
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 78)
    print(f"当前挂单  账户: {result['account']}  共 {result['count']} 笔")
    print("=" * 78)
    if not result["orders"]:
        print("  （无挂单）")
    for o in result["orders"]:
        print(f"\n  订单 {o['order_id']}  [{o['status']}]")
        print(f"    {o['contract']}  {o['action']} {o['quantity']} @ {o['order_type']}"
              f" {o.get('price') or o.get('aux_price') or ''}  TIF={o['tif']}")
        print(f"    已成交: {o['filled']}  剩余: {o['remaining']}")
    print("=" * 78)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="查询当前未完成订单")
    p.add_argument("--acc-id", default=None, help="账户 ID（多账户时若未指定且有多个账户会报错）")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_orders(args.acc_id, args.output_json)
