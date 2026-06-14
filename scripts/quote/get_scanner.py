#!/usr/bin/env python3
"""
市场扫描器 / 选股（reqScannerData）

功能：用 IBKR 内置扫描器按条件选股（涨幅榜、成交活跃、隐含波动率等）。
用法：
    python get_scanner.py                                  # 默认：美股涨幅榜 Top 25
    python get_scanner.py --scan TOP_PERC_GAIN --num 20
    python get_scanner.py --scan MOST_ACTIVE --location STK.US.MAJOR
    python get_scanner.py --scan TOP_PERC_LOSE --instrument STK --location STK.HK
    python get_scanner.py --json

常用 scanCode：
  TOP_PERC_GAIN / TOP_PERC_LOSE   涨幅/跌幅榜
  MOST_ACTIVE / HOT_BY_VOLUME     成交额/放量
  TOP_OPEN_PERC_GAIN              高开榜
  HIGH_OPT_IMP_VOLAT             高隐含波动率
  TOP_TRADE_COUNT                 成交笔数榜
常用 location：STK.US.MAJOR(美股主板) / STK.US / STK.HK / STK.EU
常用 instrument：STK / STOCK.HK / STOCK.EU / FUT.US

完整 scanCode/location 取决于账户行情权限，无权限时该榜单可能返回空或报错。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, contract_repr,
    print_result, attach_error_collector, _fail,
)


def get_scanner(scan_code="TOP_PERC_GAIN", instrument="STK", location="STK.US.MAJOR",
                num=25, output_json=False):
    ib = None
    try:
        from ib_async import ScannerSubscription
        ib = connect(readonly=True)
        errors = attach_error_collector(ib)

        sub = ScannerSubscription(
            instrument=instrument, locationCode=location,
            scanCode=scan_code, numberOfRows=num,
        )
        data = ib.reqScannerData(sub)
        rows = []
        for d in (data or []):
            c = d.contractDetails.contract if d.contractDetails else None
            rows.append({
                "rank": d.rank,
                "symbol": getattr(c, "symbol", ""),
                "contract": contract_repr(c) if c else "",
                "conId": getattr(c, "conId", 0),
                "exchange": getattr(c, "primaryExchange", "") or getattr(c, "exchange", ""),
                "currency": getattr(c, "currency", ""),
            })

        if not rows and errors:
            _fail("扫描无结果：" + "; ".join(e.get("hint") or e["msg"] for e in errors), output_json)

        result = {"scan_code": scan_code, "instrument": instrument, "location": location,
                  "count": len(rows), "results": rows}
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
    print(f"扫描器  {result['scan_code']}  ({result['instrument']} @ {result['location']})"
          f"  共 {result['count']}")
    print("=" * 64)
    print(f"  {'#':>3}  {'代码':<10} {'交易所':<10} {'货币':<5}")
    print("  " + "-" * 40)
    for r in result["results"]:
        print(f"  {r['rank']:>3}  {r['symbol']:<10} {str(r['exchange']):<10} {str(r['currency']):<5}")
    for w in result.get("warnings", []):
        print(f"\n  [提示 {w['code']}] {w.get('hint') or w['msg']}")
    print("=" * 64)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="市场扫描器/选股")
    p.add_argument("--scan", dest="scan_code", default="TOP_PERC_GAIN", help="scanCode，见文件头")
    p.add_argument("--instrument", default="STK", help="标的类型，如 STK / STOCK.HK")
    p.add_argument("--location", default="STK.US.MAJOR", help="市场，如 STK.US.MAJOR / STK.HK")
    p.add_argument("--num", type=int, default=25, help="返回行数（上限 50）")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_scanner(args.scan_code, args.instrument, args.location, args.num, args.output_json)
