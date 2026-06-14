# IBKR Skill — 盈透证券交易与行情助手

[English](README.md) | **中文**

一个 Claude Code skill,通过 [`ib_async`](https://github.com/ib-api-reloaded/ib_async)(`ib_insync` 的维护接班版)连接 **IB Gateway / TWS**,用自然语言完成 Interactive Brokers(盈透证券)的行情查询、合约解析、下单交易与账户管理。架构对标 `futuapi` skill:**每个能力 = 一个独立 CLI 脚本**,由 `SKILL.md` 调度。

---

> ## ⚠️ 免责声明
>
> 本项目**仅用于个人学习与研究**,**不构成任何投资建议**,且**不用于实盘 / 真实资金交易**。股票、期权、期货及其他衍生品交易存在重大亏损风险。软件按"现状"提供、不附带任何担保;**使用风险完全自负**,作者不对任何损失承担责任。默认面向 IBKR **模拟(paper)** 环境。

---

## 前提条件
1. **IB Gateway 或 TWS** 已启动并登录,开启 API(`Configuration → API → Settings` 勾选 *Enable ActiveX and Socket Clients*,把 `127.0.0.1` 加入 *Trusted IPs*)。下单还需**取消勾选** *Read-Only API*。
2. **Python ≥ 3.9** 与 SDK:`pip install ib_async`
3. 端口:paper Gateway `4002`、live Gateway `4001`、TWS paper `7497`、TWS live `7496`。

自检:`python scripts/check_env.py`

## 快速开始
```bash
python scripts/quote/get_snapshot.py AAPL                 # 行情快照
python scripts/quote/get_kline.py AAPL --bar 1d --num 30  # 历史 K 线
python scripts/quote/get_option_chain.py AAPL             # 期权链
python scripts/trade/get_portfolio.py                     # 持仓与资金
python scripts/trade/place_order.py --code AAPL --side BUY --quantity 10 --price 150 --preview  # 保证金/佣金预览
```
所有脚本支持 `--json`。

## 能力
- **行情**:合约详情、代码搜索、快照、L2 买卖盘、历史 K 线、分时、逐笔、交易时段、期权链、市场扫描器、基本面。
- **交易**:账户、持仓(+盈亏)、全账户持仓、PnL、下单(+whatIf `--preview`)、改单、撤单、当前挂单、历史订单、成交。
- **期权**:`plan_option.py`(只读硬止损规划器)、`place_spread.py`(定义风险的垂直借方价差)。
- **推送**:`stream_quote.py`、`stream_bars.py`。

## 安全模型
| | paper 模拟 | live 实盘 |
|---|---|---|
| 判定 | 账户号 `DU` 开头,端口 4002/7497 | 非 `DU` 账户,**或**端口 4001/7496 |
| 下单/改单/撤单 | 直接执行 | **强制 `--confirmed`**,否则只预览并 `exit 2` |

其它约束:挂单绑定固定 `clientId`(2011)保证生命周期连续;多账户拒绝瞎猜(须 `--acc-id`);改单只作用于本连接的单;所有写操作追加到 `~/.ibkr_trade_audit.jsonl`。

## 合约写法(`parse_contract`)
| 写法 | 示例 | 解析为 |
|------|------|--------|
| 裸 symbol | `AAPL` | 美股 STK/SMART/USD |
| Futu 风格前缀 | `US.AAPL` / `HK.700` | 自动映射交易所/货币(港股去前导零) |
| 冒号 mini-spec | `ES:FUT:CME:USD:20260320`、`EUR:CASH:IDEALPRO:USD` | `SYM:SECTYPE:EXCH:CCY[:EXTRA]` |

详见 `docs/CONTRACTS.md`(合约/交易所/期权写法)与 `docs/TROUBLESHOOTING.md`(错误码/排错)。

## 环境变量
| 变量 | 说明 | 默认 |
|------|------|------|
| `IB_GATEWAY_HOST` / `IB_GATEWAY_PORT` | Gateway 主机 / API 端口 | 127.0.0.1 / 4002 (paper) |
| `IB_CLIENT_ID` | 固定 clientId | 2011 |
| `IB_MARKET_DATA_TYPE` | 1实时 / 2冻结 / 3延迟 / 4延迟冻结 | 3 |
| `IB_ACCOUNT` | 默认账户(多账户须指定) | (唯一账户) |
| `IB_DEFAULT_EXCHANGE` / `IB_DEFAULT_CURRENCY` | 默认交易所/货币 | SMART / USD |

行情说明:paper/无订阅账户通常无实时行情,skill 默认走**延迟(type 3)**;`10167`/`10089` 为正常提示。准确成交量用 `get_kline.py`。

## 在另一台机器安装
```bash
git clone https://github.com/hyprh/ibkr-skill.git "~/.claude/skills/ibkr"
pip install ib_async
# 然后启动 IB Gateway / TWS 并开启 API
```

## 许可
个人学习用途,不附带任何担保。
