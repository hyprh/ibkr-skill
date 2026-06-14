#!/usr/bin/env python3
"""
获取期权链 / 到期日（reqSecDefOptParams）

功能：查询某正股的期权到期日与行权价集合。
用法：
    python get_option_chain.py AAPL                       # 列出所有到期日 + 行权价范围
    python get_option_chain.py AAPL --expiry 20260320     # 该到期日的行权价列表
    python get_option_chain.py AAPL --expiry 20260320 --around 200 --num 10   # ATM 附近 10 档
    python get_option_chain.py AAPL --json

说明：
- 返回的到期日(YYYYMMDD) 与行权价对 Call/Put 通用。
- 拿到 到期日+行权价+CALL/PUT 后，可用 get_snapshot.py / get_contract_details.py 查具体期权，
  合约写法：AAPL:OPT:SMART:USD:20260320,200,C （见 docs/CONTRACTS.md）。
- 默认取 SMART 交易所对应的链。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify,
    print_result, attach_error_collector, _fail,
)


def get_option_chain(spec, expiry=None, around=None, num=20, output_json=False):
    ib = None
    try:
        ib = connect(readonly=True)
        attach_error_collector(ib)
        underlying = qualify(ib, parse_contract(spec), output_json)

        chains = ib.reqSecDefOptParams(underlying.symbol, "", underlying.secType, underlying.conId)
        if not chains:
            _fail(f"未找到 {spec} 的期权链（该标的可能无期权）", output_json)

        # 优先 SMART 交易所
        chain = next((c for c in chains if c.exchange == "SMART"), chains[0])
        expirations = sorted(chain.expirations)
        strikes = sorted(chain.strikes)

        result = {
            "underlying": underlying.symbol, "conId": underlying.conId,
            "exchange": chain.exchange, "tradingClass": chain.tradingClass,
            "multiplier": chain.multiplier,
            "expirations": expirations,
            "expiration_count": len(expirations),
            "strike_count": len(strikes),
            "strike_min": strikes[0] if strikes else None,
            "strike_max": strikes[-1] if strikes else None,
        }

        if expiry:
            if expiry not in chain.expirations:
                _fail(f"到期日 {expiry} 不在期权链中。可用: {expirations[:12]}{' ...' if len(expirations) > 12 else ''}",
                      output_json)
            shown = strikes
            if around is not None:
                shown = sorted(strikes, key=lambda s: abs(s - around))[:num]
                shown = sorted(shown)
            result["expiry"] = expiry
            result["strikes"] = shown

        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 72)
    print(f"期权链  {result['underlying']}  (交易所 {result['exchange']}, 乘数 {result['multiplier']})")
    print("=" * 72)
    print(f"  到期日 ({result['expiration_count']} 个): "
          f"{', '.join(result['expirations'][:16])}{' ...' if result['expiration_count'] > 16 else ''}")
    print(f"  行权价: 共 {result['strike_count']} 档，范围 {result['strike_min']} ~ {result['strike_max']}")
    if "strikes" in result:
        print(f"\n  到期日 {result['expiry']} 的行权价 ({len(result['strikes'])}):")
        print("   ", ", ".join(str(s) for s in result["strikes"]))
    print("=" * 72)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="获取期权链/到期日")
    p.add_argument("spec", help="正股代码，如 AAPL / HK.700")
    p.add_argument("--expiry", default=None, help="到期日 YYYYMMDD，过滤行权价")
    p.add_argument("--around", type=float, default=None, help="围绕该价格取 ATM 附近行权价")
    p.add_argument("--num", type=int, default=20, help="配合 --around 取的档数")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_option_chain(args.spec, args.expiry, args.around, args.num, args.output_json)
