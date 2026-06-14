#!/usr/bin/env python3
"""
获取行情快照（reqMktData）

功能：获取一个或多个标的的最新价/开高低收/买卖盘/成交量。
用法：
    python get_snapshot.py AAPL
    python get_snapshot.py AAPL HK.700 MSFT
    python get_snapshot.py AAPL --mdt 1        # 1实时 2冻结 3延迟(默认) 4延迟冻结
    python get_snapshot.py AAPL --json

说明：
- paper 账户通常无实时行情订阅，默认用延迟行情（type 3）。
- 休市时段 bid/ask 可能为空，last/close 仍可返回。
- 实时行情需账户已订阅对应市场数据，否则会回退到延迟（错误 10167 是正常提示）。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify, req_snapshot,
    print_result, attach_error_collector, _fail,
)


def get_snapshot(specs, output_json=False, mdt=None, timeout=6.0):
    ib = None
    try:
        ib = connect(readonly=True, market_data_type=mdt)
        errors = attach_error_collector(ib)
        records = []
        for spec in specs:
            contract = parse_contract(spec)
            qc = qualify(ib, contract, output_json)
            snap = req_snapshot(ib, qc, timeout=timeout)
            snap["query"] = spec
            records.append(snap)
        result = {"data": records}
        if errors:
            result["warnings"] = errors
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _fmt(v):
    return "—" if v is None else v


def _print_text(result):
    print("=" * 72)
    print("行情快照")
    print("=" * 72)
    for r in result["data"]:
        print(f"\n  {r['symbol']}  ({r['exchange']} {r['currency']})  [{r['marketDataType']}]")
        print(f"    最新: {_fmt(r['last'])}  昨收: {_fmt(r['close'])}  开: {_fmt(r['open'])}"
              f"  高: {_fmt(r['high'])}  低: {_fmt(r['low'])}")
        print(f"    买一: {_fmt(r['bid'])} x {_fmt(r['bidSize'])}   "
              f"卖一: {_fmt(r['ask'])} x {_fmt(r['askSize'])}   成交量: {_fmt(r['volume'])}")
    for w in result.get("warnings", []):
        print(f"\n  [提示 {w['code']}] {w.get('hint') or w['msg']}")
    print("\n" + "=" * 72)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="获取行情快照")
    p.add_argument("specs", nargs="+", help="标的代码，如 AAPL HK.700")
    p.add_argument("--mdt", type=int, choices=[1, 2, 3, 4], default=None,
                   help="行情类型 1实时 2冻结 3延迟 4延迟冻结（默认取环境变量，3）")
    p.add_argument("--timeout", type=float, default=6.0, help="每个标的等待行情的秒数")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_snapshot(args.specs, args.output_json, args.mdt, args.timeout)
