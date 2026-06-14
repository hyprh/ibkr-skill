#!/usr/bin/env python3
"""
查询成交记录（reqExecutions / fills）

功能：列出当日成交明细（含佣金，如可得）。
用法：
    python get_executions.py
    python get_executions.py --acc-id DUN512173
    python get_executions.py --json

说明：reqExecutions 默认返回当日成交。更早的历史成交需通过对账单/Flex Query。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, resolve_account, contract_repr,
    print_result, _fail, _num,
)


def get_executions(acc_id=None, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)
        account = resolve_account(ib, acc_id)
        ib.reqExecutions()  # 阻塞调用，返回时 fills() 已就绪

        records = []
        for f in ib.fills():
            ex, c = f.execution, f.contract
            if account and ex.acctNumber != account:
                continue
            cr = f.commissionReport
            records.append({
                "time": str(ex.time),
                "contract": contract_repr(c),
                "side": ex.side,           # BOT / SLD
                "shares": _num(ex.shares),
                "price": _num(ex.price),
                "exec_id": ex.execId,
                "order_id": ex.orderId,
                "commission": _num(getattr(cr, "commission", None)),
                "realized_pnl": _num(getattr(cr, "realizedPNL", None)),
            })
        result = {"account": account, "count": len(records), "fills": records}
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 80)
    print(f"成交记录  账户: {result['account']}  共 {result['count']} 笔")
    print("=" * 80)
    if not result["fills"]:
        print("  （当日无成交）")
    for f in result["fills"]:
        print(f"\n  {f['time']}  {f['contract']}")
        print(f"    {f['side']}  {f['shares']} @ {f['price']}  订单: {f['order_id']}"
              f"  佣金: {f.get('commission')}  已实现盈亏: {f.get('realized_pnl')}")
    print("=" * 80)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="查询成交记录")
    p.add_argument("--acc-id", default=None, help="账户 ID（多账户时若未指定且有多个账户会报错）")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_executions(args.acc_id, args.output_json)
