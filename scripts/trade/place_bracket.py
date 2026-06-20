#!/usr/bin/env python3
"""
括号单 / OCA 三腿单（bracket order）

功能：一次性提交三腿订单——
  - entry      : 限价 BUY（父单，限价 @--limit）
  - takeProfit : 限价 SELL @--target（子单，止盈）
  - stopLoss   : STP   SELL @--stop  （子单，止损）
止盈/止损两腿绑定为 OCA（One-Cancels-All）组，挂在【交易所侧】（ocaType=1），
任一腿成交即自动撤销另一腿，无需脚本轮询。三腿同属一个父子组（parentId 指向 entry），
entry 未成交前子单处于待激活状态；entry 成交后止盈止损自动生效。

默认连接 paper Gateway（端口 4002）。

用法：
    # paper 提交三腿括号单（DU 账户 / 4002 无需 --confirmed）
    python place_bracket.py --code AAPL --side BUY --quantity 10 --limit 150 --stop 145 --target 160
    # 指定 TIF（默认 GTC，挂单跨交易日有效，适合波段持仓）
    python place_bracket.py --code AAPL --side BUY --quantity 10 --limit 150 --stop 145 --target 160 --tif GTC
    # whatIf 预览（仅预览 entry 腿的保证金/佣金，不下单）
    python place_bracket.py --code AAPL --side BUY --quantity 10 --limit 150 --stop 145 --target 160 --preview whatIf
    # 实盘提交（需 --confirmed，且账户为 U 开头）
    python place_bracket.py --code AAPL --side BUY --quantity 1 --limit 150 --stop 145 --target 160 --confirmed

安全约束（代码硬约束，沿用 place_order.py）：
- 实盘环境（账户号非 DU 开头，或连接 live 端口 4001/7496）提交**必须**带 --confirmed，
  否则只打印预览并退出(code 2)。绝不在无 --confirmed 时对实盘下单。
- 若 Gateway 处于 Read-Only API 只读模式，下单会被拒绝（错误 321），脚本会给出明确提示。

参数：
- --code     : 标的代码，如 AAPL / HK.700
- --side     : 入场方向（BUY/SELL）；当前实验仅做多 BUY 入场
- --quantity : 数量（正数）
- --limit    : entry 限价
- --stop     : stopLoss 止损价（STP 触发价）
- --target   : takeProfit 止盈限价
- --tif      : 有效期 GTC(默认) / DAY / IOC / OPG
- --preview  : 传 whatIf 时仅对 entry 腿做 whatIf 预览（保证金/佣金），不真正下单
- --confirmed: 实盘提交确认标志

--json 输出（契约 [F]）：
    { entry_order_id, stop_order_id, target_order_id, entry_fill_price, commission, status }
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
    LimitOrder, StopOrder,
)


def _validate_bracket(side, limit, stop, target, output_json):
    """三腿价格自洽校验（仅做多 BUY 入场：stop < limit < target）。
    价格写反会让 OCA 失去意义甚至立即触发，这里提前拦截。"""
    action = side.upper()
    if limit is None or limit <= 0:
        _fail("entry 限价 --limit 必须为正数", output_json)
    if stop is None or stop <= 0:
        _fail("止损价 --stop 必须为正数", output_json)
    if target is None or target <= 0:
        _fail("止盈价 --target 必须为正数", output_json)
    if action == "BUY":
        if not (stop < limit < target):
            _fail(f"做多括号单价格须满足 止损 < 入场 < 止盈，当前 "
                  f"stop={stop} limit={limit} target={target}", output_json)
    else:  # SELL 入场（做空）：target < limit < stop
        if not (target < limit < stop):
            _fail(f"做空括号单价格须满足 止盈 < 入场 < 止损，当前 "
                  f"target={target} limit={limit} stop={stop}", output_json)


def _build_bracket(ib, side, quantity, limit, stop, target, tif, account):
    """显式构造三腿括号单（不用 ib.bracketOrder helper，以便精确控制 OCA/TIF/account/parentId）。

    - entry      : LMT 入场，transmit=False（先不发，等子单挂好）
    - takeProfit : LMT 平仓，反向，parentId=entry，transmit=False，OCA 组
    - stopLoss   : STP 平仓，反向，parentId=entry，transmit=True（最后一腿统一 transmit 整组）
    止盈/止损用同一 ocaGroup + ocaType=1（交易所侧 OCA，按比例减量取消，最稳健）。
    """
    action = side.upper()
    reverse = "SELL" if action == "BUY" else "BUY"

    # 父单 entry：先拿一个 orderId，子单 parentId 指向它
    entry_id = ib.client.getReqId()
    entry = LimitOrder(action, quantity, limit, orderId=entry_id, transmit=False)
    entry.tif = tif.upper()
    entry.account = account

    # OCA 组名：用 entry orderId 保证唯一，避免与并发的其它括号单串组
    oca_group = f"BR_{entry_id}"

    target_id = ib.client.getReqId()
    take_profit = LimitOrder(reverse, quantity, target, orderId=target_id,
                             parentId=entry_id, transmit=False)
    take_profit.tif = tif.upper()
    take_profit.account = account
    take_profit.ocaGroup = oca_group
    take_profit.ocaType = 1  # 1=取消剩余并按比例减量（交易所侧 OCA）

    stop_id = ib.client.getReqId()
    stop_loss = StopOrder(reverse, quantity, stop, orderId=stop_id,
                          parentId=entry_id, transmit=True)  # 最后一腿 transmit 整组
    stop_loss.tif = tif.upper()
    stop_loss.account = account
    stop_loss.ocaGroup = oca_group
    stop_loss.ocaType = 1

    return entry, take_profit, stop_loss


def _wait_for_status(ib, trade, deadline=8.0):
    """事件驱动等待 entry 腿离开瞬态或截止；与 place_order._wait_for_status 同步逻辑。"""
    import time
    end = time.time() + deadline
    transient = {"", "PendingSubmit", "ApiPending", "ValidationError"}
    while time.time() < end:
        ib.waitOnUpdate(timeout=0.5)
        st = trade.orderStatus.status
        if st not in transient:
            if st in ("Filled", "Cancelled", "ApiCancelled", "Inactive"):
                break
            ib.waitOnUpdate(timeout=0.3)
            break
    if trade.orderStatus.status in transient:
        try:
            ib.reqAllOpenOrders()
            ib.sleep(0.5)
        except Exception:
            pass
    return trade.orderStatus


def _extract_fill(trade):
    """从 entry 腿的 fills 汇总真实成交均价 + 累计佣金。
    - 成交均价优先用 orderStatus.avgFillPrice，回退到 fills 的加权均价。
    - 佣金累加各 fill 的 commissionReport.commission（可能尚未回填，为 None）。
    返回 (fill_price 或 None, commission 或 None)。"""
    fill_price = _num(getattr(trade.orderStatus, "avgFillPrice", None))

    total_qty = 0.0
    weighted = 0.0
    commission = None
    for f in (trade.fills or []):
        ex = getattr(f, "execution", None)
        shares = _num(getattr(ex, "shares", None)) if ex else None
        px = _num(getattr(ex, "price", None)) if ex else None
        if shares and px is not None:
            total_qty += shares
            weighted += shares * px
        cr = getattr(f, "commissionReport", None)
        c = _num(getattr(cr, "commission", None)) if cr else None
        if c is not None:
            commission = (commission or 0.0) + c

    if fill_price is None and total_qty > 0:
        fill_price = weighted / total_qty
    return fill_price, commission


def place_bracket(code, side, quantity, limit, stop, target, tif="GTC",
                  acc_id=None, confirmed=False, preview=None, output_json=False):
    if quantity is None or quantity <= 0:
        _fail("数量必须为正数", output_json)
    _validate_bracket(side, limit, stop, target, output_json)

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
            "limit": limit, "stop": stop, "target": target, "tif": tif.upper(),
        }

        # whatIf 预览：仅对 entry 腿做预览（子单含 parentId，单独 whatIf 无意义），不下单
        if preview and str(preview).lower() == "whatif":
            entry_preview = LimitOrder(side.upper(), quantity, limit)
            entry_preview.tif = tif.upper()
            entry_preview.account = account
            state = ib.whatIfOrder(qc, entry_preview)
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
                print("=" * 60); print("括号单预览（whatIf，仅 entry 腿，未下单）"); print("=" * 60)
                print(f"  合约    : {summary['contract']}  {summary['side']} {quantity}")
                print(f"  entry 限价 : {limit}   止损: {stop}   止盈: {target}   TIF: {summary['tif']}")
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
            account, confirmed, "括号单下单",
            [f"合约: {summary['contract']}", f"入场方向: {summary['side']}", f"数量: {quantity}",
             f"entry 限价: {limit}", f"止损价: {stop}", f"止盈价: {target}", f"TIF: {summary['tif']}"],
            output_json,
        )

        entry, take_profit, stop_loss = _build_bracket(
            ib, side, quantity, limit, stop, target, tif, account)

        # 依序提交三腿：entry 与 takeProfit 不 transmit，stopLoss transmit=True 统一发出整组
        entry_trade = ib.placeOrder(qc, entry)
        target_trade = ib.placeOrder(qc, take_profit)
        stop_trade = ib.placeOrder(qc, stop_loss)

        entry_order_id = entry_trade.order.orderId
        target_order_id = target_trade.order.orderId
        stop_order_id = stop_trade.order.orderId

        # 等 entry 腿状态收敛（成交/工作态/拒绝）
        ost = _wait_for_status(ib, entry_trade)
        status = ost.status

        # 拒单判定：blocking 错误 或 entry 进入拒绝态
        blocking = [e for e in errors if e["code"] in (321, 201)]
        rejected = bool(blocking) or status in REJECTED_STATUSES
        if rejected:
            hint = "; ".join(e.get("hint") or e["msg"] for e in blocking) or f"状态 {status}"
            # entry 被拒后，已提交的子单若仍在途，尽力撤掉避免裸挂单
            for t in (entry_trade, target_trade, stop_trade):
                try:
                    if t.orderStatus.status not in REJECTED_STATUSES | {"Filled"}:
                        ib.cancelOrder(t.order)
                except Exception:
                    pass
            audit_log({"action": "place_bracket", "result": "rejected", **summary,
                       "entry_order_id": entry_order_id, "stop_order_id": stop_order_id,
                       "target_order_id": target_order_id, "status": status, "error": hint})
            _fail(f"括号单未成功（entry 状态 {status or 'N/A'}）：{hint}", output_json)

        entry_fill_price, commission = _extract_fill(entry_trade)

        # 【critical】校验两条保护腿(之前从不检查→保护腿被实盘特有规则单独拒,会被误当"已保护")
        ib.waitOnUpdate(timeout=1.0)   # 给 OCA 子腿在交易所侧激活/收敛留点时间
        stop_status = stop_trade.orderStatus.status
        target_status = target_trade.orderStatus.status
        _bad = REJECTED_STATUSES | {"Inactive", "ApiCancelled", "Cancelled"}
        protected = (stop_status not in _bad) and (target_status not in _bad)

        result = {
            "entry_order_id": entry_order_id,
            "stop_order_id": stop_order_id,
            "target_order_id": target_order_id,
            "entry_fill_price": entry_fill_price,
            "commission": commission,
            "status": status or "unknown",
            "stop_status": stop_status,
            "target_status": target_status,
            "protected": protected,   # 两条保护腿都未被拒才 True;False=持仓未受完整保护
        }
        audit_log({"action": "place_bracket", **summary, **result})

        if output_json:
            print(json_dumps(result))
        else:
            header = ("括号单已提交" if status in WORKING_STATUSES or status == "Filled"
                      else "括号单状态未确认（请用 get_orders.py 复查）")
            print("=" * 60); print(header); print("=" * 60)
            print(f"  账户    : {account} ({summary['env']})")
            print(f"  合约    : {summary['contract']}   入场: {summary['side']} {quantity}")
            print(f"  entry 订单 ID : {entry_order_id}   状态: {status or 'unknown'}")
            print(f"    入场限价 : {limit}   真实成交均价: {entry_fill_price}")
            print(f"  止损 订单 ID  : {stop_order_id}    STP @ {stop}")
            print(f"  止盈 订单 ID  : {target_order_id}    LMT @ {target}")
            print(f"  止盈/止损 已绑定 OCA（交易所侧，任一成交自动撤另一腿）   TIF: {summary['tif']}")
            print(f"  佣金（已回填部分）: {commission}")
            print("=" * 60)
            for w in errors:
                print(f"  [提示 {w['code']}] {w.get('hint') or w['msg']}")
    except SystemExit:
        raise
    except Exception as e:
        audit_log({"action": "place_bracket", "result": "error", "code": code,
                   "side": side, "quantity": quantity, "error": str(e)})
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="括号单 / OCA 三腿单")
    p.add_argument("--code", required=True, help="标的代码，如 AAPL / HK.700")
    p.add_argument("--side", required=True, choices=["BUY", "SELL"], help="入场方向")
    p.add_argument("--quantity", type=float, required=True, help="数量")
    p.add_argument("--limit", type=float, required=True, help="entry 限价")
    p.add_argument("--stop", type=float, required=True, help="止损价（STP 触发价）")
    p.add_argument("--target", type=float, required=True, help="止盈限价")
    p.add_argument("--tif", default="GTC", choices=["GTC", "DAY", "IOC", "OPG"], help="有效期（默认 GTC）")
    p.add_argument("--acc-id", default=None, help="账户 ID（多账户时必填）")
    p.add_argument("--preview", default=None, help="传 whatIf 时仅预览 entry 腿（保证金/佣金），不下单")
    p.add_argument("--confirmed", action="store_true", help="实盘下单确认标志")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    place_bracket(code=args.code, side=args.side, quantity=args.quantity, limit=args.limit,
                  stop=args.stop, target=args.target, tif=args.tif, acc_id=args.acc_id,
                  confirmed=args.confirmed, preview=args.preview, output_json=args.output_json)
