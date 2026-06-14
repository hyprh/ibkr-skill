#!/usr/bin/env python3
"""
实时 5 秒 K 线推送（reqRealTimeBars，持续 N 秒）

功能：订阅标的的实时 5 秒 bar，新 bar 到达即打印，到时自动取消。
用法：
    python stream_bars.py AAPL --duration 60
    python stream_bars.py AAPL --what MIDPOINT --json

参数：
- --duration : 持续秒数（默认 60）
- --what     : TRADES(默认) / MIDPOINT / BID / ASK
- --rth      : 仅常规交易时段

说明：reqRealTimeBars 固定为 5 秒粒度，且通常需要实时行情订阅（延迟数据不支持实时 bar）；
无订阅/休市时可能收不到 bar。Ctrl+C 可提前停止。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify,
    attach_error_collector, json_dumps, _fail, _num,
)


def stream_bars(spec, duration=60, what="TRADES", rth=False, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)
        errors = attach_error_collector(ib)
        qc = qualify(ib, parse_contract(spec), output_json)

        bars = ib.reqRealTimeBars(qc, 5, what.upper(), rth)

        def _on_bar(barlist, has_new):
            if not has_new or not barlist:
                return
            b = barlist[-1]
            row = {"time": str(b.time), "open": _num(b.open_), "high": _num(b.high),
                   "low": _num(b.low), "close": _num(b.close), "volume": _num(b.volume)}
            if output_json:
                print(json_dumps(row))
            else:
                print(f"  {row['time']}  O {row['open']} H {row['high']} "
                      f"L {row['low']} C {row['close']}  V {row['volume']}")

        bars.updateEvent += _on_bar
        if not output_json:
            print(f"实时 5 秒 K 线推送 {duration}s（{what.upper()}），Ctrl+C 停止")
            print("-" * 60)
        ib.sleep(duration)
        try:
            ib.cancelRealTimeBars(bars)
        except Exception:
            pass
        if not bars and errors:
            print("  [提示] " + "; ".join(e.get("hint") or e["msg"] for e in errors))
    except KeyboardInterrupt:
        pass
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="实时 5 秒 K 线推送")
    p.add_argument("spec", help="标的代码，如 AAPL / HK.700")
    p.add_argument("--duration", type=int, default=60, help="持续秒数")
    p.add_argument("--what", default="TRADES", choices=["TRADES", "MIDPOINT", "BID", "ASK"], help="数据类型")
    p.add_argument("--rth", action="store_true", help="仅常规交易时段")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 NDJSON")
    args = p.parse_args()
    stream_bars(args.spec, args.duration, args.what, args.rth, args.output_json)
