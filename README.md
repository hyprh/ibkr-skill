# IBKR Skill — Interactive Brokers 交易与行情助手

一个 Claude Code skill，通过 [`ib_async`](https://github.com/ib-api-reloaded/ib_async)（`ib_insync` 的官方维护接班版）连接 **IB Gateway / TWS**，用自然语言完成 Interactive Brokers（盈透证券）的行情查询、合约解析、下单交易与账户管理。设计上对标 `futuapi` skill：**每个能力 = 一个独立 CLI 脚本**，`SKILL.md` 负责调度。

> ⚠️ 交易涉及真实资金。本 skill **默认连接 paper（模拟）Gateway**（端口 4002）。实盘环境（账户号非 `DU` 开头，或连接 live 端口 4001/7496）下，下单/改单/撤单都**强制要求 `--confirmed`**。

## 前提条件

1. **IB Gateway 或 TWS** 已启动并登录，且开启 API：
   `Configuration → API → Settings` → 勾选 *Enable ActiveX and Socket Clients*，把 `127.0.0.1` 加入 *Trusted IPs*。下单还需**取消勾选** *Read-Only API*。
2. **Python ≥ 3.9** 与 SDK：
   ```bash
   pip install ib_async
   ```
3. 端口：paper Gateway `4002`、live Gateway `4001`、TWS paper `7497`、TWS live `7496`。

环境自检：
```bash
python scripts/check_env.py
```

## 快速开始

```bash
# 行情
python scripts/quote/get_snapshot.py AAPL                 # 快照
python scripts/quote/get_kline.py AAPL --bar 1d --num 30  # 历史 K 线
python scripts/quote/get_option_chain.py AAPL             # 期权链
python scripts/quote/search_symbols.py apple              # 代码搜索

# 账户 / 交易
python scripts/trade/get_portfolio.py                     # 持仓与资金
python scripts/trade/place_order.py --code AAPL --side BUY --quantity 10 --price 150 --preview  # 下单前看保证金/佣金
python scripts/trade/place_order.py --code AAPL --side BUY --quantity 10 --price 150            # paper 直接下单
python scripts/trade/get_orders.py                        # 当前挂单
python scripts/trade/cancel_order.py --order-id 12        # 撤单
```

所有脚本支持 `--json` 输出，便于程序解析。

## 能力一览

| 类别 | 脚本 | 说明 | IBKR API |
|------|------|------|----------|
| 行情 | `quote/get_contract_details.py` | 合约解析（conId/交易所/交易时段） | reqContractDetails |
| 行情 | `quote/search_symbols.py` | 代码搜索 / 合约匹配 | reqMatchingSymbols |
| 行情 | `quote/get_snapshot.py` | 行情快照（最新/开高低收/买卖盘） | reqMktData |
| 行情 | `quote/get_orderbook.py` | 买卖盘深度（L2） | reqMktDepth |
| 行情 | `quote/get_kline.py` | 历史 K 线（OHLCV） | reqHistoricalData |
| 行情 | `quote/get_intraday.py` | 分时（当日 1 分钟） | reqHistoricalData |
| 行情 | `quote/get_ticks.py` | 逐笔成交 | reqHistoricalTicks |
| 行情 | `quote/get_trading_hours.py` | 交易时段 / 是否开市 | reqContractDetails |
| 行情 | `quote/get_option_chain.py` | 期权链 / 到期日 / 行权价 | reqSecDefOptParams |
| 行情 | `quote/get_scanner.py` | 市场扫描器 / 选股 | reqScannerData |
| 行情 | `quote/get_fundamentals.py` | 基本面 / 公司信息 | reqFundamentalData |
| 交易 | `trade/get_accounts.py` | 账户列表（标注 paper/live） | managedAccounts |
| 交易 | `trade/get_portfolio.py` | 持仓 + 资金 + 盈亏 | positions / accountSummary / reqPnL |
| 交易 | `trade/get_all_portfolios.py` | 全账户持仓与资金 | positions / accountSummary |
| 交易 | `trade/get_pnl.py` | 盈亏 PnL（账户级 + 逐持仓） | reqPnL / reqPnLSingle |
| 交易 | `trade/place_order.py` | 下单（含 `--preview` whatIf） | placeOrder / whatIfOrder |
| 交易 | `trade/modify_order.py` | 改单（价/止损价/数量） | placeOrder（同 orderId） |
| 交易 | `trade/cancel_order.py` | 撤单（单笔 / 按账户 / 全部） | cancelOrder |
| 交易 | `trade/get_orders.py` | 当前挂单 | reqAllOpenOrders |
| 交易 | `trade/get_history_orders.py` | 历史 / 已完成订单 | reqCompletedOrders |
| 交易 | `trade/get_executions.py` | 成交记录 | reqExecutions |
| 推送 | `subscribe/stream_quote.py` | 实时报价推送（N 秒） | reqMktData |
| 推送 | `subscribe/stream_bars.py` | 实时 5 秒 K 线推送 | reqRealTimeBars |

## 安全模型

| | paper 模拟 | live 实盘 |
|---|---|---|
| 判定 | 账户号 `DU` 开头，端口 4002/7497 | 账户号非 `DU`，**或**端口 4001/7496 |
| 下单/改单/撤单 | 直接执行 | **强制 `--confirmed`**，否则只打印预览并 `exit(2)` |
| 资金 | 虚拟 | 真实 |

其它硬约束：
- **`--confirmed` 缺失即预览**：实盘三类写操作不带 `--confirmed` 只返回订单摘要，不执行。
- **改单只动本连接的单**：IBKR 挂单绑定下单时的 `clientId`；改其它 client/手工单会被拒（避免误下成新单）。
- **多账户拒绝瞎猜**：登录下有多个账户而未指定 `--acc-id` 时，交易脚本报错而非默认第一个。
- **交易审计**：下单/改单/撤单自动追加到 `~/.ibkr_trade_audit.jsonl`（权限 0o600、超 5MB 轮转、写失败有告警）。

## 标的 / 合约写法

`common.py:parse_contract()` 支持三种输入（详见 [`docs/CONTRACTS.md`](docs/CONTRACTS.md)）：

| 写法 | 示例 | 解析 |
|------|------|------|
| 裸 symbol | `AAPL` | 美股 STK/SMART/USD |
| Futu 风格前缀 | `US.AAPL` / `HK.700` | 自动映射交易所/货币（港股去前导零） |
| 冒号 mini-spec | `ES:FUT:CME:USD:20260320`、`EUR:CASH:IDEALPRO:USD` | `SYM:SECTYPE:EXCH:CCY[:EXTRA]` |

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `IB_GATEWAY_HOST` | Gateway/TWS 主机 | 127.0.0.1 |
| `IB_GATEWAY_PORT` | API 端口 | 4002（paper） |
| `IB_CLIENT_ID` | 固定 clientId | 2011 |
| `IB_MARKET_DATA_TYPE` | 行情类型 1实时/2冻结/3延迟/4延迟冻结 | 3 |
| `IB_ACCOUNT` | 默认账户 | （唯一账户） |
| `IB_DEFAULT_EXCHANGE` / `IB_DEFAULT_CURRENCY` | 默认交易所/货币 | SMART / USD |

> **clientId 很关键**：IBKR 挂单绑定下单时的 clientId，本 skill 默认固定 `2011`，才能让 下单→查单→改单→撤单 跨脚本调用可见可管。与 TWS GUI 等冲突报 326 时改 `IB_CLIENT_ID`。

## 目录结构

```
ibkr/
├── SKILL.md                 # 调度大脑：触发词、命令速查、安全规则
├── README.md                # 本文件
├── docs/
│   ├── CONTRACTS.md         # 合约解析、交易所代码、期权写法
│   └── TROUBLESHOOTING.md   # 错误码、行情类型、限频、排错
└── scripts/
    ├── common.py            # 共享层：连接 / 合约解析 / NaN-safe JSON / 审计 / 错误码
    ├── check_env.py         # 环境自检
    ├── quote/               # 行情类脚本
    ├── trade/               # 交易类脚本
    └── subscribe/           # 实时推送脚本
```

## 排错

常见错误（321 只读模式、326 clientId 冲突、10167/10089 无行情订阅、10197 竞争会话、492 扫描器权限、多账户需 `--acc-id` 等）的解决办法见 [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)。

## 行情说明

paper 账户通常无实时行情订阅，默认使用**延迟行情（type 3）**；`10167`/`10089` 是正常提示。准确成交量请用 `get_kline.py`（快照的延迟 volume 字段不可靠，已做清洗）。

## 免责声明

本工具用于自助接入个人 IBKR 账户进行行情查询与交易自动化。**交易有风险，实盘操作由用户自行确认与负责。** 默认 paper 环境，请在充分测试后再切换实盘。
