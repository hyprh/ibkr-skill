#!/usr/bin/env python3
"""
实时报价推送（流式 reqMktData，持续 N 秒）

功能：订阅一个或多个标的的实时报价，按间隔持续打印 last/bid/ask，到时自动取消订阅。
用法：
    python stream_quote.py AAPL --duration 30
    python stream_quote.py AAPL MSFT --interval 2 --duration 60
    python stream_quote.py AAPL --json        # 每个间隔输出一行 NDJSON

参数：
- --duration : 持续秒数（默认 30）
- --interval : 打印间隔秒数（默认 2）
- --mdt      : 行情类型 1实时/2冻结/3延迟(默认)/4延迟冻结

说明：paper/无实时订阅时为延迟数据；休市时段更新很少。Ctrl+C 可提前停止。
"""
import argparse
import sys
import time
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify,
    attach_error_collector, json_dumps, _fail, _price, _num,
)


def stream_quote(specs, duration=30, interval=2.0, mdt=None, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True, market_data_type=mdt)
        attach_error_collector(ib)
        tickers = []
        for s in specs:
            qc = qualify(ib, parse_contract(s), output_json)
            tickers.append((s, qc, ib.reqMktData(qc, "", False, False)))

        if not output_json:
            print(f"实时报价推送 {duration}s（间隔 {interval}s），Ctrl+C 停止")
            print("-" * 60)
        end = time.time() + duration
        while time.time() < end:
            ib.sleep(interval)
            ts = time.strftime("%H:%M:%S")
            for s, qc, t in tickers:
                row = {"time": ts, "symbol": qc.symbol, "last": _price(t.last),
                       "bid": _price(t.bid), "ask": _price(t.ask), "volume": _num(t.volume)}
                if output_json:
                    print(json_dumps(row))
                else:
                    print(f"  {ts}  {qc.symbol:<8} 最新 {row['last']}  买 {row['bid']}  卖 {row['ask']}")
        for s, qc, t in tickers:
            try:
                ib.cancelMktData(qc)
            except Exception:
                pass
    except KeyboardInterrupt:
        pass
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="实时报价推送")
    p.add_argument("specs", nargs="+", help="标的代码，如 AAPL MSFT")
    p.add_argument("--duration", type=int, default=30, help="持续秒数")
    p.add_argument("--interval", type=float, default=2.0, help="打印间隔秒数")
    p.add_argument("--mdt", type=int, choices=[1, 2, 3, 4], default=None, help="行情类型")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 NDJSON")
    args = p.parse_args()
    stream_quote(args.specs, args.duration, args.interval, args.mdt, args.output_json)
