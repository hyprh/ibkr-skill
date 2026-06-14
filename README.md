# IBKR Skill — Interactive Brokers Trading & Market-Data Assistant

**English** | [中文](README.zh-CN.md)

A Claude Code skill that talks to **IB Gateway / TWS** through [`ib_async`](https://github.com/ib-api-reloaded/ib_async) (the maintained `ib_insync` fork). It lets you use natural language for Interactive Brokers market data, contract resolution, order placement, and account management. Architecture mirrors the `futuapi` skill: **one capability = one standalone CLI script**, dispatched by `SKILL.md`.

---

> ## ⚠️ Disclaimer
>
> This project is for **personal learning and research only**. It is **NOT financial advice** and is **NOT intended for live / real-money trading**. Trading stocks, options, futures and other derivatives carries a substantial risk of loss. The software is provided "as is", without warranty of any kind; **use entirely at your own risk** and the authors accept no liability for any loss. By default it targets the IBKR **paper (simulated)** environment.

---

## Prerequisites
1. **IB Gateway or TWS** running and logged in, with the API enabled (`Configuration → API → Settings` → check *Enable ActiveX and Socket Clients*, add `127.0.0.1` to *Trusted IPs*). For order placement, also **uncheck** *Read-Only API*.
2. **Python ≥ 3.9** and the SDK: `pip install ib_async`
3. Ports: paper Gateway `4002`, live Gateway `4001`, TWS paper `7497`, TWS live `7496`.

Self-check: `python scripts/check_env.py`

## Quick start
```bash
python scripts/quote/get_snapshot.py AAPL                 # quote snapshot
python scripts/quote/get_kline.py AAPL --bar 1d --num 30  # historical candles
python scripts/quote/get_option_chain.py AAPL             # option chain
python scripts/trade/get_portfolio.py                     # positions & funds
python scripts/trade/place_order.py --code AAPL --side BUY --quantity 10 --price 150 --preview  # margin/commission preview
```
All scripts support `--json`.

## Capabilities
- **Quote:** contract details, symbol search, snapshot, L2 order book, historical K-line, intraday, tick-by-tick, trading hours, option chain, market scanner, fundamentals.
- **Trade:** accounts, portfolio (+PnL), all-accounts portfolio, PnL, place order (+whatIf `--preview`), modify, cancel, open orders, completed orders, executions.
- **Options:** `plan_option.py` (read-only hard-stop planner), `place_spread.py` (defined-risk vertical debit spreads).
- **Streaming:** `stream_quote.py`, `stream_bars.py`.

## Safety model
| | paper (simulated) | live (real money) |
|---|---|---|
| Detected by | account starts with `DU`, port 4002/7497 | non-`DU` account, **or** port 4001/7496 |
| place / modify / cancel | run directly | **require `--confirmed`** (else preview-only, `exit 2`) |

Other guards: orders bound to a fixed `clientId` (2011) for lifecycle continuity; multi-account refuses to guess (requires `--acc-id`); modify only acts on this client's own orders; every order mutation is appended to `~/.ibkr_trade_audit.jsonl`.

## Contract syntax (`parse_contract`)
| Form | Example | Resolves to |
|------|---------|-------------|
| bare symbol | `AAPL` | US stock STK/SMART/USD |
| Futu-style prefix | `US.AAPL` / `HK.700` | maps exchange/currency (HK strips leading zeros) |
| colon mini-spec | `ES:FUT:CME:USD:20260320`, `EUR:CASH:IDEALPRO:USD` | `SYM:SECTYPE:EXCH:CCY[:EXTRA]` |

See `docs/CONTRACTS.md` for details and `docs/TROUBLESHOOTING.md` for error codes.

## Environment variables
| Var | Meaning | Default |
|-----|---------|---------|
| `IB_GATEWAY_HOST` / `IB_GATEWAY_PORT` | Gateway host / API port | 127.0.0.1 / 4002 (paper) |
| `IB_CLIENT_ID` | fixed clientId | 2011 |
| `IB_MARKET_DATA_TYPE` | 1 live / 2 frozen / 3 delayed / 4 delayed-frozen | 3 |
| `IB_ACCOUNT` | default account (multi-account must specify) | (sole account) |
| `IB_DEFAULT_EXCHANGE` / `IB_DEFAULT_CURRENCY` | defaults | SMART / USD |

Market data note: a paper / unsubscribed account usually has no real-time data, so the skill defaults to **delayed (type 3)**; errors `10167`/`10089` are normal. Use `get_kline.py` for accurate volume.

## Install on another machine
```bash
git clone https://github.com/hyprh/ibkr-skill.git "~/.claude/skills/ibkr"
pip install ib_async
# then start IB Gateway / TWS and enable the API
```

## License
Personal, educational use. No warranty.
