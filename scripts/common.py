#!/usr/bin/env python3
"""
公共工具模块 - 提供 IBKR (Interactive Brokers) 脚本的通用功能

底层 SDK: ib_async (ib_insync 的官方维护接班版)
连接对象: IB Gateway / TWS 的 API socket 网关

包含：
- 环境变量配置
- 依赖检查与 Gateway 连通性检查（带 1 小时缓存）
- 连接管理（clientId 自动分配，避免冲突）
- 合约解析（symbol / Futu 风格前缀 / 冒号 mini-spec -> ib_async Contract）
- 行情类型设置（实时/冻结/延迟/延迟冻结）
- 账户辅助（paper / live 判定）
- 安全的 JSON / 文本输出辅助
"""
import os
import sys
import json
import time
import random
import socket
import tempfile

# ============================================================
# Windows UTF-8 输出
# ============================================================

def _ensure_utf8_io():
    """Windows 下切换 stdout/stderr 为 UTF-8，避免 GBK 编码错误"""
    if sys.platform != "win32":
        return
    for stream in ("stdout", "stderr"):
        try:
            getattr(sys, stream).reconfigure(encoding="utf-8")
        except Exception:
            pass


_ensure_utf8_io()


# ============================================================
# 环境变量配置
# ============================================================

class IBConfig:
    """IBKR 连接配置（从环境变量读取）

    | 变量 | 说明 | 默认值 |
    |------|------|--------|
    | IB_GATEWAY_HOST     | Gateway/TWS 主机          | 127.0.0.1 |
    | IB_GATEWAY_PORT     | API 端口                  | 4002 (paper Gateway) |
    | IB_CLIENT_ID        | 固定 clientId             | 2011 (DEFAULT_CLIENT_ID) |
    | IB_MARKET_DATA_TYPE | 行情类型 1实时/2冻结/3延迟/4延迟冻结 | 3 (延迟) |
    | IB_ACCOUNT          | 默认账户 ID               | （唯一账户；多账户须显式指定） |
    | IB_DEFAULT_EXCHANGE | 默认交易所                | SMART |
    | IB_DEFAULT_CURRENCY | 默认货币                  | USD |
    | IB_CONNECT_TIMEOUT  | 连接超时（秒）            | 15 |
    """
    def __init__(self):
        self.host = os.getenv("IB_GATEWAY_HOST", "127.0.0.1")
        self.port = int(os.getenv("IB_GATEWAY_PORT", "4002"))
        cid = os.getenv("IB_CLIENT_ID", "").strip()
        self.client_id = int(cid) if cid else None
        self.market_data_type = int(os.getenv("IB_MARKET_DATA_TYPE", "3"))
        self.account = os.getenv("IB_ACCOUNT", "").strip() or None
        self.default_exchange = os.getenv("IB_DEFAULT_EXCHANGE", "SMART")
        self.default_currency = os.getenv("IB_DEFAULT_CURRENCY", "USD")
        self.connect_timeout = float(os.getenv("IB_CONNECT_TIMEOUT", "15"))


def get_config():
    return IBConfig()


# ============================================================
# 依赖检查（带缓存，对齐 futuapi 风格）
# ============================================================

MIN_SDK_VERSION = (2, 0, 0)
SKILL_VERSION = "0.1.0"
_ENV_CHECK_CACHE_FILE = os.path.join(tempfile.gettempdir(), ".ibkr_env_ok")
_ENV_CHECK_TTL = 3600  # 1 小时


def _parse_version(ver_str):
    try:
        return tuple(int(x) for x in str(ver_str).strip().split(".")[:3])
    except (ValueError, AttributeError):
        return (0,)


def _env_check_is_cached():
    try:
        return (time.time() - os.path.getmtime(_ENV_CHECK_CACHE_FILE)) < _ENV_CHECK_TTL
    except OSError:
        return False


def _env_check_mark_ok():
    try:
        with open(_ENV_CHECK_CACHE_FILE, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def _check_port_reachable(host, port):
    """检查 Gateway 端口是否可连接，不可连接时报错退出"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect((host, port))
    except (ConnectionRefusedError, OSError) as e:
        print(f"[ERROR] 无法连接 IB Gateway ({host}:{port}): {e}")
        print("请先启动 IB Gateway / TWS 并登录，确认 API 端口已开启（Configuration -> API -> Settings）。")
        print("paper 默认端口 4002，live 默认 4001（TWS 为 7497/7496）。")
        sys.exit(1)
    finally:
        sock.close()


def ensure_ib_api():
    """导入期环境检查：仅校验 ib_async 是否安装 + 版本（带缓存）。
    Gateway 端口连通性不在此处检查，改由 connect() 在真正连接时检查——
    这样 `python xxx.py --help` 等无需 Gateway 即可运行，且避免重复探测。"""
    if _env_check_is_cached():
        return True
    try:
        import ib_async
        cur = _parse_version(getattr(ib_async, "__version__", "0"))
        if cur < MIN_SDK_VERSION:
            print(f"[WARN] ib_async 版本过低: {getattr(ib_async, '__version__', '?')} < "
                  f"{'.'.join(map(str, MIN_SDK_VERSION))}，建议升级: pip install --upgrade ib_async",
                  file=sys.stderr)
    except ImportError:
        print("[ERROR] 未安装 ib_async，请运行: pip install ib_async")
        sys.exit(1)
    _env_check_mark_ok()
    return True


ensure_ib_api()

from ib_async import (  # noqa: E402
    IB,
    Contract,
    Stock,
    Option,
    Future,
    Forex,
    Index,
    Order,
    LimitOrder,
    MarketOrder,
    StopOrder,
    util,
)

# 静默 ib_async 的 INFO 噪声，只保留错误
try:
    util.logToConsole("CRITICAL")
except Exception:
    pass


# ============================================================
# 连接管理
# ============================================================

# 固定默认 clientId：IBKR 的挂单与其下单时的 clientId 绑定，必须用固定 ID
# 才能让 下单 -> 查单 -> 改单 -> 撤单 这条链路跨多次脚本调用可见可管。
# 可用环境变量 IB_CLIENT_ID 覆盖（若与 TWS GUI 等其它连接冲突会报 326）。
DEFAULT_CLIENT_ID = 2011


def connect(client_id=None, market_data_type=None, readonly=False):
    """连接 IB Gateway / TWS，返回已连接的 IB 实例。

    - client_id: 不传则用环境变量 IB_CLIENT_ID，再不传则用固定的 DEFAULT_CLIENT_ID。
                 用固定 ID 才能让挂单在多次脚本调用间可见可管理（IBKR 挂单绑定 clientId）。
    - market_data_type: 行情类型，不传则用环境变量（默认 3 延迟）
    - readonly: True 时声明只读连接，跳过下单同步，适合纯行情/查询脚本
    """
    cfg = get_config()
    _check_port_reachable(cfg.host, cfg.port)
    ib = IB()
    base_cid = client_id or cfg.client_id or DEFAULT_CLIENT_ID

    # 候选 clientId 列表：
    # - readonly（纯行情/查询）允许 326 冲突时自动换随机 ID 重试，因为不涉及挂单归属。
    # - 非 readonly（下单/改单/撤单）必须固定 ID（挂单绑定 clientId），不自动换，只给出真实提示。
    candidates = [base_cid]
    if readonly:
        candidates += [random.randint(1000, 9999) for _ in range(3)]

    last_err = None
    for cid in candidates:
        try:
            ib.connect(cfg.host, cfg.port, clientId=cid, timeout=cfg.connect_timeout,
                       readonly=readonly)
            last_err = None
            break
        except Exception as e:
            last_err = e
            msg = str(e)
            is_cid_conflict = "326" in msg or "client id" in msg.lower()
            if is_cid_conflict and readonly and cid != candidates[-1]:
                continue  # 只读连接：换下一个候选 ID 再试
            if is_cid_conflict:
                print(f"[ERROR] clientId {cid} 已被占用（被 TWS GUI 或其它脚本连接持有）。"
                      f"请关闭占用它的连接，或设置环境变量 IB_CLIENT_ID 指定其它 ID 后重试。")
            else:
                print(f"[ERROR] 连接 IB Gateway 失败 ({cfg.host}:{cfg.port}): {e}")
                print("请确认 Gateway 已登录、API 已启用、本机 IP 在 Trusted IPs 中。")
            sys.exit(1)
    if last_err is not None:
        print(f"[ERROR] 连接 IB Gateway 失败 ({cfg.host}:{cfg.port}): {last_err}")
        sys.exit(1)

    mdt = market_data_type if market_data_type is not None else cfg.market_data_type
    try:
        ib.reqMarketDataType(mdt)
    except Exception:
        pass
    return ib


def safe_disconnect(ib):
    try:
        if ib and ib.isConnected():
            ib.disconnect()
    except Exception:
        pass


# ============================================================
# 账户辅助
# ============================================================

LIVE_PORTS = {4001, 7496}  # IB Gateway live / TWS live


def is_live_account(acc_id):
    """IBKR 账户号：'DU' 开头 = paper 模拟账户；其它（含空/未知）= 视为 live。
    **fail-safe**：账户号空/未知时返回 True（按实盘对待，强制确认），宁可多确认不可误放行。"""
    if not acc_id:
        return True
    return not str(acc_id).upper().startswith("DU")


def is_live_env(acc_id):
    """综合判定是否实盘环境：账户号判定 OR 连接端口为 live 端口（纵深防御）。"""
    cfg = get_config()
    return is_live_account(acc_id) or cfg.port in LIVE_PORTS


def resolve_account(ib, acc_id=None):
    """确定要使用的账户 ID。
    优先级：显式参数 > 环境变量 IB_ACCOUNT > 唯一账户。
    多账户且未指定时报错（不再静默猜 accounts[0]，避免对错账户下单）。
    """
    cfg = get_config()
    accounts = [a for a in ib.managedAccounts() if a]
    target = acc_id or cfg.account
    if target:
        if target not in accounts and accounts:
            raise ValueError(f"账户 {target} 不在当前登录的账户列表 {accounts} 中")
        return target
    if not accounts:
        raise ValueError("未找到任何 managed account，请确认 Gateway 已登录")
    if len(accounts) > 1:
        raise ValueError(
            f"登录下有多个账户 {accounts}，请用 --acc-id 明确指定（避免对错误账户操作）")
    return accounts[0]


# 订单进入有效工作/成交状态的判定（用于区分「真的提交成功」与「被拒/未生效」）
WORKING_STATUSES = {"PreSubmitted", "Submitted", "Filled", "PendingSubmit", "PendingCancel"}
REJECTED_STATUSES = {"Cancelled", "ApiCancelled", "Inactive"}


def require_live_confirmation(account, confirmed, action, detail_lines, output_json):
    """实盘安全门（place/modify/cancel 共用）：实盘环境且未 --confirmed 时打印预览并 exit(2)。"""
    if not is_live_env(account) or confirmed:
        return
    preview = {"action": f"{action}_preview", "account": account, "env": "live",
               "message": f"⚠️ 实盘{action}需确认。核对无误后加 --confirmed 重新执行。",
               "details": detail_lines}
    if output_json:
        print(json_dumps(preview))
    else:
        print("=" * 60)
        print(f"⚠️ 实盘{action}预览（未执行）—— 账户 {account}")
        print("=" * 60)
        for line in detail_lines:
            print(f"  {line}")
        print("=" * 60)
        print("请确认后加 --confirmed 重新执行。")
    sys.exit(2)


# ============================================================
# 合约解析
#   支持三种写法：
#   1. 裸 symbol            : AAPL              -> 美股 STK SMART USD
#   2. Futu 风格前缀         : US.AAPL / HK.700  -> 自动映射交易所/货币
#   3. 冒号 mini-spec        : SYM:SECTYPE:EXCH:CCY[:EXPIRY]
#      例: AAPL:STK:SMART:USD
#          700:STK:SEHK:HKD
#          ESH6:FUT:CME:USD  或  ES:FUT:CME:USD:20260320
#          EUR:CASH:IDEALPRO:USD
# ============================================================

# Futu 风格市场前缀 -> (交易所, 货币, 是否去前导零)
_PREFIX_MAP = {
    "US": ("SMART", "USD", False),
    "HK": ("SEHK", "HKD", True),    # IBKR 港股 symbol 不含前导零，如腾讯 700
    "SH": ("SEHKNTL", "CNH", False),  # 沪股通（北向），需相应权限
    "SZ": ("SEHKSZSE", "CNH", False),  # 深股通（北向），需相应权限
    "SG": ("SGX", "SGD", False),
}

_SECTYPE_ALIASES = {
    "STK": "STK", "STOCK": "STK", "股票": "STK",
    "OPT": "OPT", "OPTION": "OPT", "期权": "OPT",
    "FUT": "FUT", "FUTURE": "FUT", "期货": "FUT",
    "CASH": "CASH", "FX": "CASH", "FOREX": "CASH", "外汇": "CASH",
    "IND": "IND", "INDEX": "IND", "指数": "IND",
    "CFD": "CFD", "BOND": "BOND", "FUND": "FUND",
}


def parse_contract(spec):
    """将用户输入的标的字符串解析为 ib_async Contract（未 qualify）。"""
    cfg = get_config()
    spec = str(spec).strip()
    if not spec:
        raise ValueError("标的代码不能为空")

    # 3. 冒号 mini-spec
    if ":" in spec:
        parts = spec.split(":")
        symbol = parts[0].strip().upper()
        sectype = _SECTYPE_ALIASES.get(parts[1].strip().upper(), parts[1].strip().upper()) if len(parts) > 1 else "STK"
        exchange = parts[2].strip().upper() if len(parts) > 2 and parts[2].strip() else cfg.default_exchange
        currency = parts[3].strip().upper() if len(parts) > 3 and parts[3].strip() else cfg.default_currency
        extra = parts[4].strip() if len(parts) > 4 else ""
        return _build_contract(symbol, sectype, exchange, currency, extra)

    # 2. Futu 风格前缀  US.AAPL / HK.00700
    if "." in spec:
        prefix, rest = spec.split(".", 1)
        prefix = prefix.upper()
        if prefix in _PREFIX_MAP:
            exchange, currency, strip_zeros = _PREFIX_MAP[prefix]
            symbol = rest.strip()
            if strip_zeros and symbol.isdigit():
                symbol = str(int(symbol))  # 00700 -> 700
            return Stock(symbol.upper() if not symbol.isdigit() else symbol, exchange, currency)
        # 含点但不是已知前缀，当作裸 symbol 处理（如 BRK.B）
    # 1. 裸 symbol -> 美股
    return Stock(spec.upper(), cfg.default_exchange, cfg.default_currency)


def _build_contract(symbol, sectype, exchange, currency, extra=""):
    if sectype == "STK":
        return Stock(symbol, exchange, currency)
    if sectype == "CASH":
        # extra 可指定对手货币；exchange 默认 IDEALPRO
        return Forex(pair=f"{symbol}{currency}") if len(symbol) == 3 and len(currency) == 3 else \
            Contract(secType="CASH", symbol=symbol, exchange=exchange or "IDEALPRO", currency=currency)
    if sectype == "IND":
        return Index(symbol, exchange, currency)
    if sectype == "FUT":
        c = Future(symbol=symbol, exchange=exchange, currency=currency)
        if extra:
            c.lastTradeDateOrContractMonth = extra  # YYYYMM 或 YYYYMMDD
        return c
    if sectype == "OPT":
        # 期权建议用 get_option_chain.py / get_contract_details.py 确认；这里仅支持完整 extra=EXPIRY,STRIKE,RIGHT
        c = Contract(secType="OPT", symbol=symbol, exchange=exchange or "SMART", currency=currency)
        if extra:
            f = extra.split(",")
            if len(f) >= 1 and f[0]:
                c.lastTradeDateOrContractMonth = f[0]
            if len(f) >= 2 and f[1]:
                c.strike = float(f[1])
            if len(f) >= 3 and f[2]:
                c.right = f[2].upper()[0]
        return c
    return Contract(secType=sectype, symbol=symbol, exchange=exchange, currency=currency)


def qualify(ib, contract, output_json=False):
    """qualify 合约（补全 conId 等）。失败则报错退出。返回 qualify 后的合约。"""
    try:
        results = ib.qualifyContracts(contract)
    except Exception as e:
        _fail(f"合约解析失败: {e}", output_json)
    # 过滤掉 None / 无 conId 的结果（某些 ib_async 版本会塞 None 进来）
    results = [r for r in (results or []) if r is not None and getattr(r, "conId", 0)]
    if not results:
        _fail(f"无法解析合约: {contract_repr(contract)}（symbol/secType/exchange/currency 是否正确？）",
              output_json)
    return results[0]


def try_qualify(ib, contract):
    """非退出版 qualify：成功返回 qualify 后的合约，失败返回 None（不报错退出）。"""
    try:
        results = ib.qualifyContracts(contract)
    except Exception:
        return None
    results = [r for r in (results or []) if r is not None and getattr(r, "conId", 0)]
    return results[0] if results else None


def contract_repr(c):
    """合约的简短可读表示"""
    bits = [getattr(c, "symbol", "")]
    st = getattr(c, "secType", "")
    if st and st != "STK":
        bits.append(st)
    exch = getattr(c, "exchange", "")
    if exch:
        bits.append(exch)
    cur = getattr(c, "currency", "")
    if cur:
        bits.append(cur)
    expiry = getattr(c, "lastTradeDateOrContractMonth", "")
    if expiry:
        bits.append(str(expiry))
    strike = getattr(c, "strike", 0)
    if strike:
        bits.append(f"{getattr(c, 'right', '')}{strike}")
    return " ".join(str(b) for b in bits if b)


# ============================================================
# 行情快照辅助
# ============================================================

# 行情类型 -> 可读名
MDT_NAMES = {1: "实时", 2: "冻结", 3: "延迟", 4: "延迟冻结"}


def req_snapshot(ib, contract, timeout=6.0):
    """请求流式行情，等待字段填充后返回 dict。比 snapshot=True 对延迟数据更可靠。"""
    ticker = ib.reqMktData(contract, "", snapshot=False, regulatorySnapshot=False)
    deadline = time.time() + timeout
    while time.time() < deadline:
        ib.sleep(0.25)
        # 拿到 last 或 close 即可返回（休市时只有 close）
        if _has_value(ticker.last) or _has_value(ticker.close):
            if _has_value(ticker.bid) or _has_value(ticker.ask) or time.time() > deadline - timeout + 2.5:
                break
    try:
        ib.cancelMktData(contract)
    except Exception:
        pass
    return _ticker_to_dict(ticker, contract)


def _has_value(v):
    import math
    return v is not None and not (isinstance(v, float) and math.isnan(v)) and v != -1


def _ticker_to_dict(t, contract):
    # 延迟行情有时给出 0.0（未推送）或异常巨大的 volume，这里做清洗
    vol = _num(t.volume)
    if vol is not None and vol > 1e11:  # 个股不可能有此量级，判为脏数据
        vol = None
    return {
        "symbol": getattr(contract, "symbol", ""),
        "conId": getattr(contract, "conId", 0),
        "exchange": getattr(contract, "exchange", ""),
        "currency": getattr(contract, "currency", ""),
        "marketDataType": MDT_NAMES.get(getattr(t, "marketDataType", 0), str(getattr(t, "marketDataType", ""))),
        "last": _price(t.last),
        "close": _price(t.close),
        "open": _price(t.open),
        "high": _price(t.high),
        "low": _price(t.low),
        "bid": _price(t.bid),
        "ask": _price(t.ask),
        "bidSize": _num(t.bidSize),
        "askSize": _num(t.askSize),
        "volume": vol,
    }


# ============================================================
# 输出辅助
# ============================================================

def _num(v, default=None):
    import math
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f) or f == -1:
            return default
        return f
    except (ValueError, TypeError):
        return default


def _price(v, default=None):
    """价格字段：在 _num 基础上再把 0.0 视为「未推送」-> None（价格不会是 0）"""
    n = _num(v)
    if n is None or n == 0.0:
        return default
    return n


def dash(v, placeholder="—"):
    """文本展示用：None -> 占位符（统一各脚本的空值显示，替代各处重复的 _f/_fmt）。"""
    return placeholder if v is None else v


def _sanitize_json(obj):
    """递归把 NaN/Infinity 转为 None，避免 json.dumps 产出非法 JSON（NaN/Infinity 不是合法 JSON）。"""
    import math
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    return obj


def json_dumps(obj):
    """统一的 JSON 序列化：清洗 NaN/Inf + allow_nan=False，保证下游 (JS/jq/Go) 能解析。"""
    return json.dumps(_sanitize_json(obj), ensure_ascii=False, allow_nan=False, default=str)


# ============================================================
# 交易审计日志（place/modify/cancel 共用，单一实现）
# ============================================================

AUDIT_FILE = os.path.join(os.path.expanduser("~"), ".ibkr_trade_audit.jsonl")
_AUDIT_MAX_BYTES = 5 * 1024 * 1024  # 5MB，超过则轮转一次


def audit_log(entry):
    """追加交易审计到 ~/.ibkr_trade_audit.jsonl。
    - 权限 0o600（仅 POSIX 生效；Windows 上 mode 基本被忽略，依赖用户主目录默认 ACL，不是全局可读）
    - 超过 5MB 轮转为 .1
    - 写失败时打印 stderr 警告（不静默吞掉，否则交易无记录却无人知）
    """
    import datetime
    try:
        entry = dict(entry)
        entry["timestamp"] = datetime.datetime.now().isoformat()
        # 轮转
        try:
            if os.path.exists(AUDIT_FILE) and os.path.getsize(AUDIT_FILE) > _AUDIT_MAX_BYTES:
                bak = AUDIT_FILE + ".1"
                if os.path.exists(bak):
                    os.remove(bak)
                os.replace(AUDIT_FILE, bak)
        except OSError:
            pass
        # 受限权限创建/追加
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        fd = os.open(AUDIT_FILE, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(_sanitize_json(entry), ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"[WARN] 审计日志写入失败（交易仍会执行，但本次无记录）: {e}", file=sys.stderr)


def _fail(msg, output_json=False, code=1):
    if output_json:
        print(json_dumps({"error": str(msg)}))
    else:
        print(f"错误: {msg}")
    sys.exit(code)


def print_result(obj, output_json, text_fn=None):
    """统一输出：--json 走 JSON，否则走 text_fn(obj)"""
    if output_json:
        print(json_dumps(obj))
    elif text_fn:
        text_fn(obj)
    else:
        print(obj)


# ============================================================
# IB 错误码 -> 友好提示
# ============================================================

def explain_error(code, msg=""):
    hints = {
        326: "clientId 冲突：换一个 IB_CLIENT_ID 或重试。",
        321: "Gateway 处于「Read-Only API」只读模式：请在 Gateway -> Configuration -> API -> Settings 取消勾选 “Read-Only API” 后重试，方可下单/改单/撤单。",
        10167: "无实时行情订阅，已回退到延迟数据（这是正常的，paper 账户常见）。",
        10197: "有竞争性会话（同一账户已在别处登录 TWS/手机/网页），导致本次取不到行情。请退出其他登录或稍后重试。",
        10089: "该合约的实时行情需要额外订阅；可用延迟行情（IB_MARKET_DATA_TYPE=3）。",
        200: "合约未找到或模糊：检查 symbol / secType / exchange / currency，或用 get_contract_details.py 解析。",
        201: "下单被拒绝：检查账户权限、资金、合约是否可交易。",
        202: "订单已撤销。",
        354: "未订阅该行情数据。",
        2104: "行情数据农场连接正常（信息提示，可忽略）。",
        2106: "历史数据农场连接正常（信息提示，可忽略）。",
        2158: "行情数据农场连接正常（信息提示，可忽略）。",
    }
    return hints.get(code, "")


# 仅信息性、可忽略的错误码
INFO_ERROR_CODES = {2104, 2106, 2107, 2108, 2158, 2119, 10167}


_UESCAPE_RE = __import__("re").compile(r"\\u([0-9a-fA-F]{4})")


def decode_ib_msg(msg):
    """中文版 Gateway 会把非英文消息发成字面量 \\uXXXX 转义串，这里逐个还原为可读中文。
    用正则只替换合法的 \\uXXXX token，对夹杂反斜杠/Windows 路径的消息也安全、永不抛错。"""
    s = str(msg)
    if "\\u" not in s:
        return s
    try:
        return _UESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), s)
    except Exception:
        return s


def attach_error_collector(ib):
    """挂载错误收集器，返回 list；过滤掉纯信息性提示。"""
    errors = []

    def _on_error(reqId, code, msg, contract):
        if code not in INFO_ERROR_CODES:
            errors.append({"code": code, "msg": decode_ib_msg(msg), "hint": explain_error(code, msg)})

    ib.errorEvent += _on_error
    return errors
