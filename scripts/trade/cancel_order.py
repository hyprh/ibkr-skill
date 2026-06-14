#!/usr/bin/env python3
"""
撤单（cancelOrder）

功能：撤销指定 orderId 的挂单，或撤销某账户全部挂单。
用法：
    python cancel_order.py --order-id 12
    python cancel_order.py --all --acc-id DUN512173      # 撤该账户全部挂单
    python cancel_order.py --all --all-accounts          # 撤所有账户全部挂单（危险）
    python cancel_order.py --order-id 12 --confirmed      # 实盘需 --confirmed

约束：
- 实盘环境撤单必须 --confirmed。
- --all 默认仅作用于解析出的单一账户；跨账户需显式 --all-accounts。
- 报告的状态基于撤单后的实际回报，而非「请求已发送」。
- 未提供 order-id 时可先用 get_orders.py 查询。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, resolve_account, is_live_env, contract_repr,
    attach_error_collector, audit_log, json_dumps, _fail,
)


def cancel_order(order_id=None, cancel_all=False, all_accounts=False,
                 acc_id=None, confirmed=False, output_json=False):
    if not cancel_all and order_id is None:
        _fail("请指定 --order-id 或 --all", output_json)

    ib = None
    try:
        ib = connect(readonly=False)
        errors = attach_error_collector(ib)
        ib.reqAllOpenOrders()
        open_trades = ib.openTrades()

        if cancel_all:
            if all_accounts:
                targets = list(open_trades)
                scope = "所有账户"
            else:
                account = resolve_account(ib, acc_id)  # 多账户未指定会报错，强制明确
                targets = [t for t in open_trades if t.order.account == account]
                scope = account
            if not targets:
                _fail(f"{scope} 当前没有挂单", output_json)
        else:
            targets = [t for t in open_trades if t.order.orderId == order_id]
            if not targets:
                _fail(f"未找到 orderId={order_id} 的挂单（可能已成交/已撤销）。用 get_orders.py 查询。",
                      output_json)
            scope = targets[0].order.account

        # 安全门：任一目标属于实盘环境，或 --all-accounts（杀伤面跨所有账户），都要求 --confirmed
        any_live = any(is_live_env(t.order.account) for t in targets)
        if (any_live or all_accounts) and not confirmed:
            why = "实盘" if any_live else "跨所有账户"
            detail = [f"范围: {scope}", f"将撤销 {len(targets)} 笔挂单："] + \
                     [f"  - #{t.order.orderId} {contract_repr(t.contract)} {t.order.action} {t.order.totalQuantity}"
                      for t in targets[:20]]
            if output_json:
                print(json_dumps({"action": "cancel_order_preview", "scope": scope,
                                  "env": "live" if any_live else "paper", "count": len(targets),
                                  "details": detail,
                                  "message": f"⚠️ {why}撤单需确认，加 --confirmed 重新执行。"}))
            else:
                print("=" * 56); print(f"⚠️ {why}撤单预览（未执行）—— 范围 {scope}"); print("=" * 56)
                for line in detail:
                    print(f"  {line}")
                print("=" * 56); print("请确认后加 --confirmed 重新执行。")
            sys.exit(2)

        cancelled_ids = []
        for t in targets:
            ib.cancelOrder(t.order)
            cancelled_ids.append(t.order.orderId)
        ib.sleep(1.5)

        # 基于实际状态报告
        status_map = {t.order.orderId: t.orderStatus.status for t in ib.trades()
                      if t.order.orderId in cancelled_ids}
        results = [{"order_id": oid, "status": status_map.get(oid, "unknown")}
                   for oid in cancelled_ids]
        cancelled_ok = [r for r in results if r["status"] in ("Cancelled", "ApiCancelled", "PendingCancel")]

        # 202 = 「订单已撤销」是撤单成功的回执，不算错误；只把真正阻断性的列为 warning
        blocking = [e for e in errors if e["code"] in (321, 201)]
        audit_log({"action": "cancel_order", "scope": scope, "requested": cancelled_ids,
                   "results": results, "errors": [e["msg"] for e in blocking]})

        out = {"scope": scope, "requested": cancelled_ids, "results": results,
               "cancelled_count": len(cancelled_ok)}
        if blocking:
            out["warning"] = "; ".join(e.get("hint") or e["msg"] for e in blocking)

        if output_json:
            print(json_dumps(out))
        else:
            print("=" * 56)
            print(f"撤单结果  范围: {scope}  成功 {len(cancelled_ok)}/{len(results)}")
            for r in results:
                print(f"  订单 {r['order_id']} -> {r['status']}")
            if blocking:
                print(f"  ⚠️ {out['warning']}")
            print("=" * 56)
    except SystemExit:
        raise
    except Exception as e:
        # 撤单可能已发出后才抛错，必须留下审计记录
        audit_log({"action": "cancel_order", "result": "error",
                   "order_id": order_id, "all": cancel_all, "error": str(e)})
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="撤单")
    p.add_argument("--order-id", type=int, default=None, help="订单 ID")
    p.add_argument("--all", action="store_true", dest="cancel_all", help="撤销（某账户）全部挂单")
    p.add_argument("--all-accounts", action="store_true", help="配合 --all：跨所有账户撤单")
    p.add_argument("--acc-id", default=None, help="账户 ID（--all 时用于限定范围）")
    p.add_argument("--confirmed", action="store_true", help="实盘撤单确认标志")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    cancel_order(args.order_id, args.cancel_all, args.all_accounts,
                 args.acc_id, args.confirmed, args.output_json)
