#!/usr/bin/env python3
"""
历史/已完成订单（reqCompletedOrders）

功能：列出已完成的订单（成交/撤销/失效），含成交均价与状态。
用法：
    python get_history_orders.py
    python get_history_orders.py --acc-id DUN512173
    python get_history_orders.py --status Filled [--json]

说明：
- reqCompletedOrders 返回当日及近期已完成订单（更早的需对账单/Flex Query）。
- --status 可过滤，如 Filled / Cancelled / ApiCancelled / Inactive。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, resolve_account, contract_repr,
    print_result, _fail, _num,
)


def get_history_orders(acc_id=None, status_filter=None, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)
        # acc_id 仅用于过滤（不强制单账户），未指定则不过滤
        from common import get_config
        account = acc_id or get_config().account

        trades = ib.reqCompletedOrders(apiOnly=False)
        rows = []
        for t in (trades or []):
            o, c, st = t.order, t.contract, t.orderStatus
            if account and o.account and o.account != account:
                continue
            if status_filter and st.status.lower() != status_filter.lower():
                continue
            # 完成时间取自最后一条 log
            when = str(t.log[-1].time) if t.log else ""
            rows.append({
                "time": when,
                "account": o.account,
                "perm_id": o.permId,
                "contract": contract_repr(c),
                "action": o.action,
                "order_type": o.orderType,
                "quantity": _num(o.totalQuantity),
                "filled": _num(st.filled),
                "avg_fill_price": _num(st.avgFillPrice) or None,
                "status": st.status,
            })
        result = {"account": account or "全部", "count": len(rows), "orders": rows}
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 80)
    print(f"历史订单  账户: {result['account']}  共 {result['count']} 笔")
    print("=" * 80)
    if not result["orders"]:
        print("  （无已完成订单）")
    for o in result["orders"]:
        print(f"\n  {o['time']}  [{o['status']}]  {o['contract']}")
        print(f"    {o['action']} {o['quantity']} @ {o['order_type']}  已成交 {o['filled']}"
              f"  均价 {o.get('avg_fill_price')}  permId {o['perm_id']}")
    print("=" * 80)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="历史/已完成订单")
    p.add_argument("--acc-id", default=None, help="账户 ID（过滤用，可选）")
    p.add_argument("--status", default=None, help="按状态过滤，如 Filled / Cancelled")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_history_orders(args.acc_id, args.status, args.output_json)
