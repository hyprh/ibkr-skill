#!/usr/bin/env python3
"""
期权方向交易规划器（买方,只读不下单）—— 用期权把"硬止损"在开仓前算清楚

功能：给定正股 + 方向(CALL/PUT) + 风险预算，自动选到期日/行权价，
      算出权利金=最大亏损(硬止损)、按预算定张数、盈亏平衡点、杠杆。**不下单。**
用法：
    # 看涨 BABA，约 35 天到期，平值，最多亏 $300
    python plan_option.py --code BABA --right CALL --max-loss 300
    # 指定到期日/行权价
    python plan_option.py --code BABA --right CALL --expiry 20260717 --strike 115 --max-loss 500
    # 按账户净值 1% 定风险(需连账户)
    python plan_option.py --code QQQ --right CALL --risk-pct 1 --acc-id U18026371 --json

参数：
- --right     : CALL(看涨) / PUT(看跌)
- --dte       : 目标到期天数(默认 35)，自动选最接近的到期日
- --strike    : 指定行权价；不给则按 --moneyness 选
- --moneyness : ATM(平值,默认) / ITM(实值) / OTM(虚值)
- --offset    : 配合 ITM/OTM，偏离档数(默认 1)
- --max-loss  : 本笔最大亏损预算(美元)，用于定张数
- --risk-pct  : 改用账户净值的百分比定风险(需 --acc-id / 能连账户)
- 硬止损 = 总权利金 = 选定方案的最大亏损，跳空也打不穿。
"""
import argparse
import datetime
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify, try_qualify, req_snapshot,
    resolve_account, attach_error_collector, print_result, _fail, _num, _price,
    Option,
)
from common import dash as _f


def _qualify_option_near(ib, symbol, exp, strikes, target_k, right_char, currency):
    """从离 target_k 最近的行权价起逐个尝试 qualify，返回(合约, 实际行权价)。
    解决 reqSecDefOptParams 返回的是全到期日 strike 并集、某到期日未必挂该行权价的问题。"""
    for k in sorted(strikes, key=lambda s: abs(s - target_k))[:10]:
        opt = Option(symbol, exp, k, right_char, "SMART", currency=currency)
        oq = try_qualify(ib, opt)
        if oq is not None:
            return oq, k
    return None, None


def _pick_expiry(expirations, dte):
    """选最接近 today+dte 的到期日"""
    today = datetime.date.today()
    target = today + datetime.timedelta(days=dte)
    best, best_diff = None, None
    for e in sorted(expirations):
        try:
            d = datetime.datetime.strptime(e, "%Y%m%d").date()
        except ValueError:
            continue
        if d < today:
            continue
        diff = abs((d - target).days)
        if best is None or diff < best_diff:
            best, best_diff = e, diff
    return best


def _pick_strike(strikes, spot, moneyness, offset, right):
    """按平值/实值/虚值选行权价"""
    strikes = sorted(strikes)
    atm = min(strikes, key=lambda s: abs(s - spot))
    if moneyness == "ATM":
        return atm
    i = strikes.index(atm)
    # CALL: 实值=低于现价(更小行权价)，虚值=高于；PUT 相反
    if right == "CALL":
        i = i - offset if moneyness == "ITM" else i + offset
    else:
        i = i + offset if moneyness == "ITM" else i - offset
    i = max(0, min(len(strikes) - 1, i))
    return strikes[i]


def plan_option(code, right, dte=35, expiry=None, strike=None, moneyness="ATM", offset=1,
                max_loss=None, risk_pct=None, acc_id=None, output_json=False):
    right = right.upper()
    if right not in ("CALL", "PUT"):
        _fail("--right 必须是 CALL 或 PUT", output_json)
    ib = None
    try:
        ib = connect(readonly=True)
        attach_error_collector(ib)
        underlying = qualify(ib, parse_contract(code), output_json)

        # 现价(可能因休市/竞争会话取不到;给了 --strike 就不强求)
        snap = req_snapshot(ib, underlying, timeout=5)
        spot = snap.get("last") or snap.get("close")
        if spot is None and strike is None:
            _fail(f"取不到 {code} 现价且未指定 --strike，无法选行权价。"
                  f"请加 --strike，或稍后重试(可能是竞争会话 10197)。", output_json)

        # 期权链
        chains = ib.reqSecDefOptParams(underlying.symbol, "", underlying.secType, underlying.conId)
        if not chains:
            _fail(f"{code} 无期权链", output_json)
        chain = next((c for c in chains if c.exchange == "SMART"), chains[0])
        expirations, strikes = sorted(chain.expirations), sorted(chain.strikes)

        if expiry:
            if expiry not in chain.expirations:
                _fail(f"到期日 {expiry} 不在链中。可用: {expirations[:10]}…", output_json)
            exp = expiry
        else:
            exp = _pick_expiry(expirations, dte)
        if not exp:
            _fail("找不到合适到期日", output_json)
        target_k = float(strike) if strike is not None else _pick_strike(strikes, spot, moneyness.upper(), offset, right)
        right_char = "C" if right == "CALL" else "P"

        # 从目标行权价就近找该到期日实际挂牌的合约
        oq, k = _qualify_option_near(ib, underlying.symbol, exp, strikes, target_k, right_char,
                                     underlying.currency)
        if oq is None:
            _fail(f"{underlying.symbol} {exp} 附近找不到可交易的 {right} 合约(该到期日可能未挂此行权价),"
                  f"换个到期日或行权价试试。", output_json)
        osnap = req_snapshot(ib, oq, timeout=5)
        # 买入成本优先用 ask，回退 last/close/中价
        ask, bid, last, close = osnap.get("ask"), osnap.get("bid"), osnap.get("last"), osnap.get("close")
        prem = ask or last or close or ((bid + ask) / 2 if bid and ask else None)

        mult = 100
        result = {
            "underlying": underlying.symbol, "spot": spot,
            "option": {"expiry": exp, "strike": k, "right": right,
                       "premium_ask": ask, "premium_last": last, "premium_used": prem},
            "multiplier": mult,
        }

        if prem is None:
            result["note"] = "暂无期权报价(休市/无期权行情订阅);已选好合约,补到报价即可算硬止损与张数。"
            print_result(result, output_json, _print_text)
            return

        prem_per_contract = prem * mult           # 一张的权利金 = 一张的最大亏损
        # 风险预算
        budget = None
        if max_loss is not None:
            budget = float(max_loss)
        elif risk_pct is not None:
            account = resolve_account(ib, acc_id)
            netliq = None
            for v in ib.accountSummary(account):
                if v.account == account and v.tag == "NetLiquidation":
                    netliq = _num(v.value); break
            if netliq:
                budget = netliq * float(risk_pct) / 100.0
        qty = int(budget // prem_per_contract) if budget else None
        budget_note = None
        if budget and qty == 0:
            budget_note = f"预算 ${budget:.0f} 不足以买 1 张(单张需 ${prem_per_contract:.0f})"

        breakeven = (k + prem) if right == "CALL" else (k - prem)
        be_move_pct = None
        if spot:
            be_move_pct = (breakeven - spot) / spot * 100 if right == "CALL" else (spot - breakeven) / spot * 100

        result["plan"] = {
            "premium_per_contract": round(prem_per_contract, 2),
            "risk_budget": round(budget, 2) if budget else None,
            "contracts": qty,
            "max_loss_total": round(prem_per_contract * qty, 2) if qty else None,  # 硬止损
            "breakeven": round(breakeven, 4),
            "breakeven_move_pct": round(be_move_pct, 2) if be_move_pct is not None else None,
            "notional_exposure": round(k * mult * qty, 2) if qty else None,
            "budget_note": budget_note,
        }
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        if _os.getenv("IBKR_DEBUG"):
            import traceback
            traceback.print_exc()
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    o = result["option"]
    print("=" * 64)
    print(f"期权规划  {result['underlying']}  现价 {_f(result['spot'])}")
    print("=" * 64)
    print(f"  选定合约: {result['underlying']} {o['expiry']} {o['strike']} {o['right']}")
    print(f"  权利金(ask/last): {_f(o['premium_ask'])} / {_f(o['premium_last'])}  (×{result['multiplier']})")
    if result.get("note"):
        print(f"  ⚠️ {result['note']}"); print("=" * 64); return
    p = result["plan"]
    print(f"  单张权利金(=单张最大亏损): ${_f(p['premium_per_contract'])}")
    print(f"  风险预算: ${_f(p['risk_budget'])}  →  张数: {_f(p['contracts'])}")
    if p.get("budget_note"):
        print(f"  ⚠️ {p['budget_note']}")
    print(f"  ★ 硬止损(总最大亏损): ${_f(p['max_loss_total'])}  ← 跳空也打不穿")
    print(f"  盈亏平衡: {_f(p['breakeven'])}  (需{o['right']=='CALL' and '涨' or '跌'} {_f(p['breakeven_move_pct'])}%)")
    print(f"  名义敞口: ${_f(p['notional_exposure'])}")
    print("=" * 64)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="期权方向交易规划器(只读)")
    p.add_argument("--code", required=True, help="正股代码，如 BABA / QQQ")
    p.add_argument("--right", required=True, choices=["CALL", "PUT"], help="看涨/看跌")
    p.add_argument("--dte", type=int, default=35, help="目标到期天数(默认 35)")
    p.add_argument("--expiry", default=None, help="指定到期日 YYYYMMDD(覆盖 --dte)")
    p.add_argument("--strike", type=float, default=None, help="指定行权价")
    p.add_argument("--moneyness", default="ATM", choices=["ATM", "ITM", "OTM"], help="平/实/虚值")
    p.add_argument("--offset", type=int, default=1, help="ITM/OTM 偏离档数")
    p.add_argument("--max-loss", type=float, default=None, help="本笔最大亏损预算(美元)")
    p.add_argument("--risk-pct", type=float, default=None, help="用账户净值百分比定风险")
    p.add_argument("--acc-id", default=None, help="账户 ID(配合 --risk-pct)")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON")
    args = p.parse_args()
    plan_option(args.code, args.right, args.dte, args.expiry, args.strike, args.moneyness,
                args.offset, args.max_loss, args.risk_pct, args.acc_id, args.output_json)
