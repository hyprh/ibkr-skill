# IBKR 合约（Contract）解析说明

IBKR 不用 `US.AAPL` 这种简单字符串，而是用 `Contract(symbol, secType, exchange, currency)` 四要素定位标的。本 skill 的 `common.py:parse_contract()` 支持三种输入写法，按需自动转换。

## 三种标的写法

### 1. 裸 symbol（最省事，默认美股）
```
AAPL   ->  Stock('AAPL', 'SMART', 'USD')
MSFT   ->  Stock('MSFT', 'SMART', 'USD')
```
不带任何前缀/分隔符的纯字母，一律按 **美股 STK / SMART / USD** 处理。

### 2. Futu 风格市场前缀（兼容老习惯）
| 输入 | 解析为 | 说明 |
|------|--------|------|
| `US.AAPL` | Stock('AAPL','SMART','USD') | 美股 |
| `HK.700` 或 `HK.00700` | Stock('700','SEHK','HKD') | 港股，自动去前导零 |
| `SH.600519` | Stock('600519','SEHKNTL','CNH') | 沪股通（北向），需相应权限 |
| `SZ.000001` | Stock('000001','SEHKSZSE','CNH') | 深股通（北向），需相应权限 |
| `SG.xxx` | Stock('xxx','SGX','SGD') | 新加坡 |

> 港股 IBKR symbol 不含前导零：腾讯 = `700`（不是 `00700`）。本 skill 自动处理。

### 3. 冒号 mini-spec（完整控制，适合期货/外汇/指数/非美股）
格式：`SYMBOL:SECTYPE:EXCHANGE:CURRENCY[:EXTRA]`

| 输入 | 含义 |
|------|------|
| `AAPL:STK:SMART:USD` | 美股 |
| `700:STK:SEHK:HKD` | 腾讯港股 |
| `ES:FUT:CME:USD:20260320` | E-mini S&P 期货，到期 2026-03 |
| `MES:FUT:CME:USD:202603` | Micro E-mini（EXTRA 可写 YYYYMM 或 YYYYMMDD） |
| `EUR:CASH:IDEALPRO:USD` | 欧元/美元 外汇 |
| `SPX:IND:CBOE:USD` | 标普500 指数 |
| `7203:STK:TSEJ:JPY` | 丰田（东京） |

SECTYPE 别名：`STK/股票`, `OPT/期权`, `FUT/期货`, `CASH/外汇/FX`, `IND/指数`, `CFD`, `BOND`, `FUND`。

## 常用交易所代码速查

| 市场 | exchange | currency |
|------|----------|----------|
| 美股（智能路由） | `SMART` | USD |
| 纳斯达克 / 纽交所 | `NASDAQ` / `NYSE` | USD |
| 港股 | `SEHK` | HKD |
| 沪股通 / 深股通 | `SEHKNTL` / `SEHKSZSE` | CNH |
| 东京 | `TSEJ` | JPY |
| 伦敦 | `LSE` | GBP |
| 法兰克福 | `IBIS` | EUR |
| 新加坡 | `SGX` | SGD |
| CME 期货 | `CME` / `GLOBEX` | USD |
| CBOE 指数/期权 | `CBOE` | USD |
| 外汇 | `IDEALPRO` | （对手货币） |

## 期权合约

期权用 `Option(symbol, lastTradeDateOrContractMonth, strike, right, exchange)`：
- `right`: `'C'`(Call/认购) 或 `'P'`(Put/认沽)
- `lastTradeDateOrContractMonth`: `YYYYMMDD`，如 `20260320`
- exchange 通常用 `SMART`

冒号写法（OPT 的 EXTRA = `EXPIRY,STRIKE,RIGHT`）：
```
AAPL:OPT:SMART:USD:20260320,200,C
```

> 建议：期权先用 `get_contract_details.py` 解析确认 conId，避免参数错配。

## 合约解析最佳实践

1. **下单/取行情前先 qualify**：脚本内部都会调用 `qualifyContracts` 补全 conId。
2. **歧义合约**（同名多上市地、ADR vs 本地股）：用 `get_contract_details.py SYMBOL` 查看所有匹配，确认 `primaryExchange`/`currency` 后用冒号 mini-spec 精确指定。
3. **港股代码**：记得去前导零，或直接用 `HK.700`（脚本帮你去零）。
