#!/usr/bin/env python3
"""
买卖盘 / 摆盘深度（reqMktDepth，L2 行情）

功能：获取多档买卖盘口（价格/数量/做市商或交易所）。
用法：
    python get_orderbook.py AAPL
    python get_orderbook.py AAPL --num 10 [--json]

说明：
- L2 深度行情通常需要对应市场的 **Level 2 行情订阅**，paper/无订阅时可能返回空或报错（10092 等）。
- 部分美股需用 isSmartDepth（脚本默认开启）聚合智能路由深度。
- 休市时段盘口可能为空。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify,
    print_result, attach_error_collector, _fail, _num,
)


def get_orderbook(spec, num=5, output_json=False, timeout=4.0):
    ib = None
    try:
        ib = connect(readonly=True)
        errors = attach_error_collector(ib)
        qc = qualify(ib, parse_contract(spec), output_json)

        ticker = ib.reqMktDepth(qc, numRows=num, isSmartDepth=True)
        import time
        end = time.time() + timeout
        while time.time() < end:
            ib.sleep(0.3)
            if ticker.domBids or ticker.domAsks:
                ib.sleep(0.5)
                break
        bids = [{"price": _num(l.price), "size": _num(l.size),
                 "src": getattr(l, "marketMaker", "")} for l in (ticker.domBids or [])]
        asks = [{"price": _num(l.price), "size": _num(l.size),
                 "src": getattr(l, "marketMaker", "")} for l in (ticker.domAsks or [])]
        try:
            ib.cancelMktDepth(qc, isSmartDepth=True)
        except Exception:
            pass

        result = {"symbol": qc.symbol, "bids": bids, "asks": asks}
        if not bids and not asks and errors:
            result["warnings"] = errors
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 56)
    print(f"买卖盘深度  {result['symbol']}")
    print("=" * 56)
    print(f"  {'档':>3}  {'买价':>10} {'买量':>10}   |   {'卖价':>10} {'卖量':>10}")
    print("  " + "-" * 52)
    n = max(len(result["bids"]), len(result["asks"]))
    if n == 0:
        print("  （无深度数据：可能无 L2 订阅或休市）")
    for i in range(n):
        b = result["bids"][i] if i < len(result["bids"]) else {"price": "", "size": ""}
        a = result["asks"][i] if i < len(result["asks"]) else {"price": "", "size": ""}
        print(f"  {i+1:>3}  {str(b['price']):>10} {str(b['size']):>10}   |   "
              f"{str(a['price']):>10} {str(a['size']):>10}")
    for w in result.get("warnings", []):
        print(f"\n  [提示 {w['code']}] {w.get('hint') or w['msg']}")
    print("=" * 56)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="买卖盘深度 (L2)")
    p.add_argument("spec", help="标的代码，如 AAPL / HK.700")
    p.add_argument("--num", type=int, default=5, help="档位数（默认 5）")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_orderbook(args.spec, args.num, args.output_json)
