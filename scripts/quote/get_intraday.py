#!/usr/bin/env python3
"""
分时数据（当日 1 分钟 OHLCV，reqHistoricalData）

功能：获取标的当日（或最近一个交易日）的分时序列（默认 1 分钟 bar）。
用法：
    python get_intraday.py AAPL
    python get_intraday.py AAPL --bar 5m --rth        # 仅常规时段
    python get_intraday.py AAPL --tail 30 --json      # 只看最后 30 根

参数：
- --bar  : 分时粒度 1m(默认)/2m/3m/5m/15m/30m
- --rth  : 仅常规交易时段（默认含盘前盘后）
- --tail : 只显示最后 N 根（默认全部）
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify,
    print_result, attach_error_collector, _fail, _num,
)

_BAR_MAP = {"1m": "1 min", "2m": "2 mins", "3m": "3 mins", "5m": "5 mins",
            "15m": "15 mins", "30m": "30 mins"}


def get_intraday(spec, bar="1m", rth=False, tail=None, output_json=False):
    ib = None
    try:
        bar_size = _BAR_MAP.get(bar)
        if not bar_size:
            _fail(f"不支持的分时粒度: {bar}，可选 {', '.join(_BAR_MAP)}", output_json)
        ib = connect(readonly=True)
        errors = attach_error_collector(ib)
        qc = qualify(ib, parse_contract(spec), output_json)

        bars = ib.reqHistoricalData(qc, endDateTime="", durationStr="1 D",
                                    barSizeSetting=bar_size, whatToShow="TRADES",
                                    useRTH=rth, formatDate=1)
        if not bars:
            msg = f"未取到 {spec} 的分时数据"
            if errors:
                msg += "（" + "; ".join(e.get("hint") or e["msg"] for e in errors) + "）"
            _fail(msg, output_json)

        rows = [{"time": str(b.date), "open": _num(b.open), "high": _num(b.high),
                 "low": _num(b.low), "close": _num(b.close), "volume": _num(b.volume)}
                for b in bars]
        if tail and tail > 0:
            rows = rows[-tail:]
        result = {"symbol": qc.symbol, "bar": bar, "useRTH": rth, "count": len(rows), "bars": rows}
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _f(v):
    return "—" if v is None else v


def _print_text(result):
    print("=" * 70)
    print(f"分时  {result['symbol']}  ({result['bar']}, RTH={result['useRTH']})  共 {result['count']} 根")
    print("=" * 70)
    print(f"  {'时间':<22} {'开':>9} {'高':>9} {'低':>9} {'收':>9} {'量':>11}")
    print("  " + "-" * 68)
    for b in result["bars"]:
        print(f"  {b['time']:<22} {str(_f(b['open'])):>9} {str(_f(b['high'])):>9} "
              f"{str(_f(b['low'])):>9} {str(_f(b['close'])):>9} {str(_f(b['volume'])):>11}")
    print("=" * 70)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="分时数据（当日 OHLCV）")
    p.add_argument("spec", help="标的代码，如 AAPL / HK.700")
    p.add_argument("--bar", default="1m", help="分时粒度 1m/2m/3m/5m/15m/30m")
    p.add_argument("--rth", action="store_true", help="仅常规交易时段")
    p.add_argument("--tail", type=int, default=None, help="只显示最后 N 根")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_intraday(args.spec, args.bar, args.rth, args.tail, args.output_json)
