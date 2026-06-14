#!/usr/bin/env python3
"""
逐笔成交 / 历史 Tick（reqHistoricalTicks）

功能：获取最近 N 笔逐笔成交（或买卖盘 tick）。
用法：
    python get_ticks.py AAPL                      # 最近 50 笔成交
    python get_ticks.py AAPL --num 100
    python get_ticks.py AAPL --what BID_ASK       # 买卖盘 tick
    python get_ticks.py AAPL --end "20260612 16:00:00 US/Eastern"
    python get_ticks.py AAPL --json

参数：
- --what : TRADES(默认逐笔成交) / BID_ASK / MIDPOINT
- --num  : 笔数（单次上限 1000）
- --end  : 截止时间（默认当前），格式 "YYYYMMDD HH:MM:SS 时区"
- --rth  : 仅常规交易时段
"""
import argparse
import datetime
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify,
    print_result, attach_error_collector, _fail, _num,
)


def get_ticks(spec, num=50, what="TRADES", end="", rth=False, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)
        errors = attach_error_collector(ib)
        qc = qualify(ib, parse_contract(spec), output_json)

        what = what.upper()
        # reqHistoricalTicks 必须恰好指定 start/end 之一；end 为空时用当前时间
        end_dt = end if end else datetime.datetime.now()
        ticks = ib.reqHistoricalTicks(qc, "", end_dt, num, what, useRth=rth)
        rows = []
        for t in (ticks or []):
            if what == "BID_ASK":
                rows.append({"time": str(t.time),
                             "bid": _num(getattr(t, "priceBid", None)),
                             "ask": _num(getattr(t, "priceAsk", None)),
                             "bidSize": _num(getattr(t, "sizeBid", None)),
                             "askSize": _num(getattr(t, "sizeAsk", None))})
            elif what == "MIDPOINT":
                rows.append({"time": str(t.time), "price": _num(getattr(t, "price", None))})
            else:  # TRADES
                rows.append({"time": str(t.time), "price": _num(t.price), "size": _num(t.size),
                             "exchange": getattr(t, "exchange", "")})

        if not rows and errors:
            _fail("未取到逐笔数据：" + "; ".join(e.get("hint") or e["msg"] for e in errors), output_json)
        result = {"symbol": qc.symbol, "what": what, "count": len(rows), "ticks": rows}
        if errors:
            result["warnings"] = errors
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 64)
    print(f"逐笔  {result['symbol']}  ({result['what']})  共 {result['count']} 笔")
    print("=" * 64)
    what = result["what"]
    for r in result["ticks"]:
        if what == "BID_ASK":
            print(f"  {r['time']}   买 {r['bid']} x {r['bidSize']}   卖 {r['ask']} x {r['askSize']}")
        elif what == "MIDPOINT":
            print(f"  {r['time']}   中价 {r['price']}")
        else:
            print(f"  {r['time']}   {r['price']} x {r['size']}  @{r['exchange']}")
    for w in result.get("warnings", []):
        print(f"\n  [提示 {w['code']}] {w.get('hint') or w['msg']}")
    print("=" * 64)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="逐笔成交/历史 Tick")
    p.add_argument("spec", help="标的代码，如 AAPL / HK.700")
    p.add_argument("--num", type=int, default=50, help="笔数（上限 1000）")
    p.add_argument("--what", default="TRADES", choices=["TRADES", "BID_ASK", "MIDPOINT"], help="tick 类型")
    p.add_argument("--end", default="", help='截止时间 "YYYYMMDD HH:MM:SS 时区"，默认当前')
    p.add_argument("--rth", action="store_true", help="仅常规交易时段")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_ticks(args.spec, args.num, args.what, args.end, args.rth, args.output_json)
