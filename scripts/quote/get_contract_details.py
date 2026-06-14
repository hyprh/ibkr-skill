#!/usr/bin/env python3
"""
解析/查询合约详情（reqContractDetails）

功能：把用户输入的标的解析为 IBKR 合约，返回 conId、交易所、交易时段、最小变动价位等。
用法：
    python get_contract_details.py AAPL
    python get_contract_details.py HK.700
    python get_contract_details.py "ES:FUT:CME:USD"
    python get_contract_details.py AAPL --json

标的写法见 docs/CONTRACTS.md：
    - 裸 symbol           AAPL              -> 美股 STK SMART USD
    - Futu 风格前缀        US.AAPL / HK.700
    - 冒号 mini-spec       SYM:SECTYPE:EXCH:CCY[:EXPIRY]
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, contract_repr,
    print_result, _fail,
)


def get_contract_details(spec, output_json=False, limit=10):
    ib = None
    try:
        contract = parse_contract(spec)
        ib = connect(readonly=True)
        details = ib.reqContractDetails(contract)
        if not details:
            _fail(f"未找到合约: {contract_repr(contract)}", output_json)
        records = []
        for d in details[:limit]:
            c = d.contract
            records.append({
                "conId": c.conId,
                "symbol": c.symbol,
                "secType": c.secType,
                "exchange": c.exchange,
                "primaryExchange": c.primaryExchange,
                "currency": c.currency,
                "localSymbol": c.localSymbol,
                "tradingClass": c.tradingClass,
                "longName": d.longName,
                "minTick": d.minTick,
                "lastTradeDate": getattr(c, "lastTradeDateOrContractMonth", "") or None,
                "strike": getattr(c, "strike", 0) or None,
                "right": getattr(c, "right", "") or None,
                "tradingHours": d.tradingHours,
                "liquidHours": d.liquidHours,
                "timeZoneId": d.timeZoneId,
            })
        result = {"query": spec, "count": len(details), "contracts": records}
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 70)
    print(f"合约详情  查询: {result['query']}  匹配: {result['count']}")
    print("=" * 70)
    for r in result["contracts"]:
        print(f"\n  {r['symbol']}  {r.get('longName') or ''}  [{r['secType']}]")
        print(f"    conId: {r['conId']}  交易所: {r['exchange']}"
              f"  主交易所: {r['primaryExchange']}  货币: {r['currency']}")
        print(f"    localSymbol: {r['localSymbol']}  tradingClass: {r['tradingClass']}"
              f"  最小变动: {r['minTick']}")
        if r.get("lastTradeDate"):
            extra = f"    到期: {r['lastTradeDate']}"
            if r.get("strike"):
                extra += f"  行权价: {r['strike']}  类型: {r['right']}"
            print(extra)
        if r.get("tradingHours"):
            print(f"    交易时段: {r['tradingHours'][:60]}  时区: {r['timeZoneId']}")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="解析/查询合约详情")
    p.add_argument("spec", help="标的代码，如 AAPL / US.AAPL / HK.700 / ES:FUT:CME:USD")
    p.add_argument("--limit", type=int, default=10, help="最多返回的匹配数量")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_contract_details(args.spec, args.output_json, args.limit)
