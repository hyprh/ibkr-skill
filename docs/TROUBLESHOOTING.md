# IBKR skill 排错与常见问题

## 连接相关

| 现象 | 原因 / 解决 |
|------|------------|
| `无法连接 IB Gateway (127.0.0.1:4002)` | Gateway/TWS 未启动或未登录；或端口不对。paper Gateway=4002，live Gateway=4001，TWS paper=7497，TWS live=7496。用 `IB_GATEWAY_PORT` 配置。 |
| 错误 326 `clientId 冲突` | 同一 clientId 已被另一连接占用（如 TWS GUI、其它脚本）。设置不同的 `IB_CLIENT_ID`。本 skill 默认用固定 clientId `2011`。 |
| 连接超时 / API 未响应 | Gateway → Configuration → API → Settings 勾选 “Enable ActiveX and Socket Clients”；把 `127.0.0.1` 加入 “Trusted IPs”。 |

## 下单 / 改单 / 撤单相关

| 现象 | 原因 / 解决 |
|------|------------|
| 错误 321 + 下单失败 | **Gateway 处于 Read-Only API 只读模式**。Gateway → Configuration → API → Settings 取消勾选 “Read-Only API”，重启 API 连接后再下单。 |
| 下单后 `get_orders` 看不到该单 | IBKR 挂单**绑定下单时的 clientId**。必须用固定 clientId（本 skill 默认 2011）才能跨脚本调用看到/管理。`get_orders/cancel/modify` 用 `reqAllOpenOrders()` 可看到所有 client 的挂单。 |
| 订单一直 `PreSubmitted`、提示 399 “不会在 XX:XX 前下达交易所” | 当前是**休市时段**，限价单要到开盘才会真正进交易所。这是正常的。 |
| 改单/撤单对“别的 client 下的单”不生效 | 跨 client 的撤单多数可行，但**改单**（重发同 orderId）通常要求与下单是同一 client。用固定 clientId 下单即可避免。 |
| 孤儿挂单撤不掉（PendingCancel↔PreSubmitted 反复） | 下单的 client 已断开 + 休市，撤单无法传到交易所。开盘后会处理，或直接在 Gateway/TWS GUI 里撤。 |
| 下单后状态短暂为 `ValidationError` | 休市时 IBKR 发 399 警告（开盘前不下达）的瞬态，会收敛到 `PreSubmitted`。脚本会自动再同步一次；若仍未确认会提示用 `get_orders.py` 复查（订单其实已挂上）。 |
| 错误 202 | 「订单已撤销」的正常回执，不是错误。 |
| `登录下有多个账户 [...]，请用 --acc-id 明确指定` | 多账户登录时交易/PnL 脚本拒绝瞎猜账户，必须用 `--acc-id` 或环境变量 `IB_ACCOUNT` 指定。 |
| 改单提示「由其它 client/手工下单，本连接无法改单」 | IBKR 改单按 (clientId, orderId) 定位；只能改本连接下的单。用下单时的 clientId（设 `IB_CLIENT_ID`）或在 GUI 改。 |

## 行情相关

| 现象 | 原因 / 解决 |
|------|------------|
| 错误 10167 “无实时行情订阅，显示延迟数据” | 正常提示。paper 账户通常没有实时行情订阅，已自动回退到延迟（type 3）。 |
| 错误 10089 “需要额外订阅” | 该合约实时行情需付费订阅。用延迟行情：`--mdt 3` 或环境变量 `IB_MARKET_DATA_TYPE=3`。 |
| 错误 10197 “竞争性会话” | 同一账户已在别处登录（手机/网页/另一台 TWS）。退出其它登录，或稍后重试。 |
| 快照 `bid/ask` 为空、`open` 为 — | 休市时段没有实时买卖盘；延迟数据也常缺 open。`last/close` 仍可用。要历史 OHLCV 用 `get_kline.py`。 |
| 快照成交量异常巨大 | 延迟行情的 volume 字段不可靠，脚本已对 >1e11 的脏值置空。**准确成交量请看 `get_kline.py`**。 |
| 扫描器错误 492 / 结果不精确 | 该扫描榜单需额外行情订阅；返回的是近似结果。换 `--scan`/`--location` 或开通对应行情权限。 |

## 行情类型（reqMarketDataType）

| 值 | 含义 | 说明 |
|----|------|------|
| 1 | 实时 | 需账户已订阅对应市场数据 |
| 2 | 冻结 | 最近一次实时快照（收盘后用） |
| 3 | 延迟 | 约 15 分钟延迟，**无需订阅**（本 skill 默认） |
| 4 | 延迟冻结 | 延迟 + 冻结 |

用 `IB_MARKET_DATA_TYPE` 或脚本 `--mdt` 参数切换。

## 限频（Pacing）

- 通用：每秒不超过约 50 条消息。
- 历史数据：同一合约 10 分钟内勿超约 60 次请求；短周期 + 长 duration 易触发。
- 触发后会收到 pacing violation，等待后重试即可。

## paper vs live 判别

- 账户号 `DU` 开头 = paper 模拟；`U` 开头 = live 实盘。
- 连接端口也体现环境：4002/7497 = paper，4001/7496 = live。
- 本 skill 对 **live 账户下单强制要求 `--confirmed`**，paper 账户直接执行。

## ib_async 自定义代码模板

skill 脚本未覆盖的需求，可临时写 Python（用完即删）：

```python
import sys, os
sys.path.insert(0, r"<skill>/scripts")
from common import connect, safe_disconnect, parse_contract, qualify
ib = connect(readonly=True)
try:
    c = qualify(ib, parse_contract("AAPL"))
    # ... 调用 ib.reqXxx(...) ...
finally:
    safe_disconnect(ib)
```

期货/期权/外汇等可直接 `from ib_async import Future, Option, Forex` 自行构造合约。
