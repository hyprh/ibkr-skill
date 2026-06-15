#!/usr/bin/env python3
"""
获取历史 K 线 / Bar 数据（reqHistoricalData）

功能：获取指定标的的历史 OHLCV 数据。
用法：
    python get_kline.py AAPL                          # 默认日线，最近 30 根
    python get_kline.py AAPL --bar 1d --duration "60 D"
    python get_kline.py AAPL --bar 5m --duration "2 D"
    python get_kline.py HK.700 --bar 1d --num 20
    python get_kline.py AAPL --rth                    # 仅常规交易时段
    python get_kline.py AAPL --json

参数：
- --bar      : 1m 2m 3m 5m 15m 30m 1h 1d 1w 1M（K 线周期）
- --duration : IBKR 时长字符串，如 "30 D" "6 M" "1 Y" "2 W"（默认按 bar 推断）
- --num      : 只保留最近 N 根（在 duration 拉取后截取）
- --what     : 数据类型 TRADES(默认) / MIDPOINT / BID / ASK
- --rth      : 仅常规交易时段（默认包含盘前盘后）

说明：历史数据有 pacing 限制（同一合约 10 分钟内勿超约 60 次请求）。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify,
    print_result, attach_error_collector, _fail, _num,
)


from common import dash as _f  # 统一的 None->— 占位

# bar 周期 -> ib_async barSizeSetting
_BAR_MAP = {
    "1m": "1 min", "2m": "2 mins", "3m": "3 mins", "5m": "5 mins",
    "15m": "15 mins", "30m": "30 mins", "1h": "1 hour", "60m": "1 hour",
    "1d": "1 day", "1w": "1 week", "1M": "1 month",
}

# bar 周期 -> 默认 duration
_DEFAULT_DURATION = {
    "1 min": "1 D", "2 mins": "1 D", "3 mins": "2 D", "5 mins": "5 D",
    "15 mins": "10 D", "30 mins": "20 D", "1 hour": "30 D",
    "1 day": "60 D", "1 week": "1 Y", "1 month": "5 Y",
}


def _fmt_end(end):
    """'2022-12-31' -> '20221231 23:59:59 US/Eastern';空则返回 ''(=当前)。"""
    if not end:
        return ""
    d = str(end).replace("-", "").strip()
    return f"{d} 23:59:59 US/Eastern"


def get_kline(spec, bar="1d", duration=None, num=None, what="TRADES",
              rth=False, end="", output_json=False):
    ib = None
    try:
        bar_size = _BAR_MAP.get(bar)
        if not bar_size:
            _fail(f"不支持的 bar 周期: {bar}，可选: {', '.join(_BAR_MAP)}", output_json)
        dur = duration or _DEFAULT_DURATION.get(bar_size, "30 D")

        ib = connect(readonly=True)
        errors = attach_error_collector(ib)
        contract = parse_contract(spec)
        qc = qualify(ib, contract, output_json)

        bars = ib.reqHistoricalData(
            qc, endDateTime=_fmt_end(end), durationStr=dur, barSizeSetting=bar_size,
            whatToShow=what.upper(), useRTH=rth, formatDate=1,
        )
        if not bars:
            msg = f"未获取到 {spec} 的历史数据"
            if errors:
                msg += "（" + "; ".join(e.get("hint") or e["msg"] for e in errors) + "）"
            _fail(msg, output_json)

        # 历史 bar 在 MIDPOINT/BID/ASK 或冷门标的上可能含 NaN，过 _num 清洗为 None，
        # 否则 --json 会产出非法的 NaN token，下游解析器报错
        rows = [{
            "date": str(b.date),
            "open": _num(b.open), "high": _num(b.high), "low": _num(b.low), "close": _num(b.close),
            "volume": _num(b.volume), "wap": _num(getattr(b, "average", None)),
        } for b in bars]
        if num and num > 0:
            rows = rows[-num:]

        result = {
            "symbol": qc.symbol, "bar": bar, "duration": dur,
            "whatToShow": what.upper(), "useRTH": rth, "count": len(rows),
            "bars": rows,
        }
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
    print("=" * 78)
    print(f"K线  {result['symbol']}  周期: {result['bar']}  "
          f"({result['whatToShow']}, RTH={result['useRTH']})  共 {result['count']} 根")
    print("=" * 78)
    print(f"  {'时间':<20} {'开':>10} {'高':>10} {'低':>10} {'收':>10} {'量':>12}")
    print("  " + "-" * 76)
    for b in result["bars"]:
        print(f"  {b['date']:<20} {str(_f(b['open'])):>10} {str(_f(b['high'])):>10} "
              f"{str(_f(b['low'])):>10} {str(_f(b['close'])):>10} {str(_f(b['volume'])):>12}")
    for w in result.get("warnings", []):
        print(f"\n  [提示 {w['code']}] {w.get('hint') or w['msg']}")
    print("=" * 78)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="获取历史 K 线")
    p.add_argument("spec", help="标的代码，如 AAPL HK.700")
    p.add_argument("--bar", default="1d", help="K 线周期：1m 5m 15m 30m 1h 1d 1w 1M")
    p.add_argument("--duration", default=None, help='时长，如 "30 D" "6 M" "1 Y"')
    p.add_argument("--num", type=int, default=30, help="只保留最近 N 根（默认 30）")
    p.add_argument("--what", default="TRADES", help="TRADES / MIDPOINT / BID / ASK")
    p.add_argument("--rth", action="store_true", help="仅常规交易时段")
    p.add_argument("--end", default="", help="历史窗口截止日 YYYY-MM-DD（默认当前；配合 --duration 往回取）")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_kline(args.spec, args.bar, args.duration, args.num, args.what, args.rth,
              args.end, args.output_json)
