#!/usr/bin/env python3
"""
代码搜索 / 合约匹配（reqMatchingSymbols）

功能：按公司名或代码片段模糊搜索，返回匹配的标的（含 conId、交易所、可用衍生品类型）。
用法：
    python search_symbols.py apple
    python search_symbols.py "腾讯"
    python search_symbols.py TSLA --json

说明：用于「不知道确切代码/交易所」时定位标的；拿到后可用 get_contract_details.py 进一步确认。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import connect, safe_disconnect, print_result, _fail


def search_symbols(pattern, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)
        res = ib.reqMatchingSymbols(pattern)
        rows = []
        for cd in (res or []):
            c = cd.contract
            rows.append({
                "symbol": c.symbol,
                "secType": c.secType,
                "primaryExchange": c.primaryExchange,
                "currency": c.currency,
                "conId": c.conId,
                "description": getattr(c, "description", "") or "",
                "derivatives": list(getattr(cd, "derivativeSecTypes", []) or []),
            })
        result = {"query": pattern, "count": len(rows), "matches": rows}
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 76)
    print(f"代码搜索  '{result['query']}'  共 {result['count']} 个匹配")
    print("=" * 76)
    print(f"  {'代码':<10} {'类型':<6} {'主交易所':<12} {'货币':<5} {'衍生品'}")
    print("  " + "-" * 72)
    for r in result["matches"]:
        deriv = ",".join(r["derivatives"]) if r["derivatives"] else "-"
        print(f"  {r['symbol']:<10} {r['secType']:<6} {str(r['primaryExchange']):<12} "
              f"{str(r['currency']):<5} {deriv}")
    print("=" * 76)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="代码搜索/合约匹配")
    p.add_argument("pattern", help="公司名或代码片段，如 apple / TSLA / 腾讯")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    search_symbols(args.pattern, args.output_json)
