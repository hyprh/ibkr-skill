# IBKR Skill — Interactive Brokers Trading & Market-Data Assistant

A Claude Code skill that talks to **IB Gateway / TWS** through [`ib_async`](https://github.com/ib-api-reloaded/ib_async) (the maintained `ib_insync` fork). It lets you use natural language for Interactive Brokers market data, contract resolution, order placement, and account management. Architecture mirrors the `futuapi` skill: **one capability = one standalone CLI script**, dispatched by `SKILL.md`.

---

> ## ⚠️ Disclaimer / 免责声明
>
> **English —** This project is for **personal learning and research only**. It is **NOT financial advice** and is **NOT intended for live / real-money trading**. Trading stocks, options, futures and other derivatives carries a substantial risk of loss. The software is provided "as is", without warranty of any kind; **use entirely at your own risk** and the authors accept no liability for any loss. By default it targets the IBKR **paper (simulated)** environment.
>
> **中文 —** 本项目**仅用于个人学习与研究**,**不构成任何投资建议**,且**不用于实盘 / 真实资金交易**。股票、期权、期货及其他衍生品交易存在重大亏损风险。软件按"现状"提供、不附带任何担保;**使用风险完全自负**,作者不对任何损失承担责任。默认面向 IBKR **模拟(paper)** 环境。

---

## English

### Prerequisites
1. **IB Gateway or TWS** running and logged in, with the API enabled (`Configuration → API → Settings` → check *Enable ActiveX and Socket Clients*, add `127.0.0.1` to *Trusted IPs*). For order placement, also **uncheck** *Read-Only API*.
2. **Python ≥ 3.9** and the SDK: `pip install ib_async`
3. Ports: paper Gateway `4002`, live Gateway `4001`, TWS paper `7497`, TWS live `7496`.

Self-check: `python scripts/check_env.py`

### Quick start
```bash
python scripts/quote/get_snapshot.py AAPL                 # quote snapshot
python scripts/quote/get_kline.py AAPL --bar 1d --num 30  # historical candles
python scripts/quote/get_option_chain.py AAPL             # option chain
python scripts/trade/get_portfolio.py                     # positions & funds
python scripts/trade/place_order.py --code AAPL --side BUY --quantity 10 --price 150 --preview  # margin/commission preview
```
All scripts support `--json`.

### Capabilities
- **Quote:** contract details, symbol search, snapshot, L2 order book, historical K-line, intraday, tick-by-tick, trading hours, option chain, market scanner, fundamentals.
- **Trade:** accounts, portfolio (+PnL), all-accounts portfolio, PnL, place order (+whatIf `--preview`), modify, cancel, open orders, completed orders, executions.
- **Options:** `plan_option.py` (read-only hard-stop planner), `place_spread.py` (defined-risk vertical debit spreads).
- **Streaming:** `stream_quote.py`, `stream_bars.py`.

### Safety model
| | paper (simulated) | live (real money) |
|---|---|---|
| Detected by | account starts with `DU`, port 4002/7497 | non-`DU` account, **or** port 4001/7496 |
| place / modify / cancel | run directly | **require `--confirmed`** (else preview-only, `exit 2`) |

Other guards: orders bound to a fixed `clientId` (2011) for lifecycle continuity; multi-account refuses to guess (requires `--acc-id`); modify only acts on this client's own orders; every order mutation is appended to `~/.ibkr_trade_audit.jsonl`.

### Contract syntax (`parse_contract`)
| Form | Example | Resolves to |
|------|---------|-------------|
| bare symbol | `AAPL` | US stock STK/SMART/USD |
| Futu-style prefix | `US.AAPL` / `HK.700` | maps exchange/currency (HK strips leading zeros) |
| colon mini-spec | `ES:FUT:CME:USD:20260320`, `EUR:CASH:IDEALPRO:USD` | `SYM:SECTYPE:EXCH:CCY[:EXTRA]` |

See `docs/CONTRACTS.md` for details and `docs/TROUBLESHOOTING.md` for error codes.

### Environment variables
| Var | Meaning | Default |
|-----|---------|---------|
| `IB_GATEWAY_HOST` / `IB_GATEWAY_PORT` | Gateway host / API port | 127.0.0.1 / 4002 (paper) |
| `IB_CLIENT_ID` | fixed clientId | 2011 |
| `IB_MARKET_DATA_TYPE` | 1 live / 2 frozen / 3 delayed / 4 delayed-frozen | 3 |
| `IB_ACCOUNT` | default account (multi-account must specify) | (sole account) |
| `IB_DEFAULT_EXCHANGE` / `IB_DEFAULT_CURRENCY` | defaults | SMART / USD |

Market data note: a paper / unsubscribed account usually has no real-time data, so the skill defaults to **delayed (type 3)**; errors `10167`/`10089` are normal. Use `get_kline.py` for accurate volume.

### Install on another machine
```bash
git clone https://github.com/hyprh/ibkr-skill.git "~/.claude/skills/ibkr"
pip install ib_async
# then start IB Gateway / TWS and enable the API
```

---

## 中文

### 前提条件
1. **IB Gateway 或 TWS** 已启动并登录,开启 API(`Configuration → API → Settings` 勾选 *Enable ActiveX and Socket Clients*,把 `127.0.0.1` 加入 *Trusted IPs*)。下单还需**取消勾选** *Read-Only API*。
2. **Python ≥ 3.9** 与 SDK:`pip install ib_async`
3. 端口:paper Gateway `4002`、live Gateway `4001`、TWS paper `7497`、TWS live `7496`。

自检:`python scripts/check_env.py`

### 快速开始
```bash
python scripts/quote/get_snapshot.py AAPL                 # 行情快照
python scripts/quote/get_kline.py AAPL --bar 1d --num 30  # 历史 K 线
python scripts/quote/get_option_chain.py AAPL             # 期权链
python scripts/trade/get_portfolio.py                     # 持仓与资金
python scripts/trade/place_order.py --code AAPL --side BUY --quantity 10 --price 150 --preview  # 保证金/佣金预览
```
所有脚本支持 `--json`。

### 能力
- **行情**:合约详情、代码搜索、快照、L2 买卖盘、历史 K 线、分时、逐笔、交易时段、期权链、市场扫描器、基本面。
- **交易**:账户、持仓(+盈亏)、全账户持仓、PnL、下单(+whatIf `--preview`)、改单、撤单、当前挂单、历史订单、成交。
- **期权**:`plan_option.py`(只读硬止损规划器)、`place_spread.py`(定义风险的垂直借方价差)。
- **推送**:`stream_quote.py`、`stream_bars.py`。

### 安全模型
| | paper 模拟 | live 实盘 |
|---|---|---|
| 判定 | 账户号 `DU` 开头,端口 4002/7497 | 非 `DU` 账户,**或**端口 4001/7496 |
| 下单/改单/撤单 | 直接执行 | **强制 `--confirmed`**,否则只预览并 `exit 2` |

其它约束:挂单绑定固定 `clientId`(2011)保证生命周期连续;多账户拒绝瞎猜(须 `--acc-id`);改单只作用于本连接的单;所有写操作追加到 `~/.ibkr_trade_audit.jsonl`。

### 合约写法、环境变量、行情说明
同上方英文小节;详见 `docs/CONTRACTS.md`(合约/交易所/期权写法)与 `docs/TROUBLESHOOTING.md`(错误码/排错)。paper/无订阅账户默认延迟行情(type 3),`10167`/`10089` 为正常提示;准确成交量用 `get_kline.py`。

### 在另一台机器安装
```bash
git clone https://github.com/hyprh/ibkr-skill.git "~/.claude/skills/ibkr"
pip install ib_async
# 然后启动 IB Gateway / TWS 并开启 API
```

---

## License / 许可

Personal, educational use. No warranty. / 个人学习用途,不附带任何担保。
