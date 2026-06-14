#!/usr/bin/env python3
"""
交易时段 / 交易日历（reqContractDetails 的 tradingHours/liquidHours）

功能：显示标的的交易时段、所在时区、当前是否开市、以及未来若干个交易日的开收盘时间。
用法：
    python get_trading_hours.py AAPL
    python get_trading_hours.py HK.700 --days 5 [--json]

说明：
- liquidHours = 常规交易时段（RTH）；tradingHours = 含盘前盘后的完整时段。
- 「当前是否开市」按合约时区(timeZoneId)与 liquidHours 比对，best-effort。
"""
import argparse
import sys
import datetime
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, print_result, _fail,
)


def _parse_sessions(hours_str):
    """解析 'YYYYMMDD:HHMM-YYYYMMDD:HHMM;YYYYMMDD:CLOSED;...' -> 会话列表"""
    sessions = []
    for seg in (hours_str or "").split(";"):
        seg = seg.strip()
        if not seg:
            continue
        if ":CLOSED" in seg.upper():
            day = seg.split(":")[0]
            sessions.append({"date": day, "closed": True})
        elif "-" in seg:
            start, endp = seg.split("-", 1)
            sessions.append({"date": start.split(":")[0], "closed": False,
                             "open": start, "close": endp})
    return sessions


def _is_open_now(liquid, tz_id):
    """best-effort 判断当前是否在 liquidHours 内。失败返回 None。"""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.datetime.now(ZoneInfo(tz_id))
        for s in _parse_sessions(liquid):
            if s["closed"]:
                continue
            try:
                o = datetime.datetime.strptime(s["open"], "%Y%m%d:%H%M").replace(tzinfo=ZoneInfo(tz_id))
                c = datetime.datetime.strptime(s["close"], "%Y%m%d:%H%M").replace(tzinfo=ZoneInfo(tz_id))
            except ValueError:
                continue
            if o <= now <= c:
                return True
        return False
    except Exception:
        return None


def get_trading_hours(spec, days=3, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)
        details = ib.reqContractDetails(parse_contract(spec))
        if not details:
            _fail(f"未找到合约: {spec}", output_json)
        d = details[0]
        c = d.contract
        liquid = _parse_sessions(d.liquidHours)[:days]
        trading = _parse_sessions(d.tradingHours)[:days]
        result = {
            "symbol": c.symbol, "exchange": c.exchange, "timeZoneId": d.timeZoneId,
            "open_now": _is_open_now(d.liquidHours, d.timeZoneId),
            "liquid_hours": liquid, "trading_hours": trading,
        }
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _fmt_session(s):
    if s["closed"]:
        return f"{s['date']}  休市"
    return f"{s['open'].replace(':', ' ')} - {s['close'].split(':')[1]}"


def _print_text(result):
    print("=" * 62)
    on = result["open_now"]
    status = "🟢 开市中" if on else ("🔴 休市" if on is False else "状态未知")
    print(f"交易时段  {result['symbol']} ({result['exchange']})  时区 {result['timeZoneId']}  [{status}]")
    print("=" * 62)
    print("  常规时段(RTH / liquidHours):")
    for s in result["liquid_hours"]:
        print(f"    {_fmt_session(s)}")
    print("  完整时段(含盘前盘后 / tradingHours):")
    for s in result["trading_hours"]:
        print(f"    {_fmt_session(s)}")
    print("=" * 62)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="交易时段/交易日历")
    p.add_argument("spec", help="标的代码，如 AAPL / HK.700")
    p.add_argument("--days", type=int, default=3, help="显示未来几个交易日（默认 3）")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_trading_hours(args.spec, args.days, args.output_json)
