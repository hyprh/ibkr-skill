#!/usr/bin/env python3
"""
基本面 / 公司信息（reqFundamentalData）

功能：获取公司概况、财务摘要、财务比率等基本面数据（来自 Reuters/Refinitiv）。
用法：
    python get_fundamentals.py AAPL                       # 公司概况快照
    python get_fundamentals.py AAPL --report finsummary
    python get_fundamentals.py AAPL --report ratios --raw --json

参数 --report：
  snapshot(默认)  公司概况(ReportSnapshot)
  finsummary      财务摘要(ReportsFinSummary)
  ratios          财务比率(ReportRatios)
  statements      财务报表(ReportsFinStatements)
  calendar        财报日历(CalendarReport)
--raw : 输出原始 XML（默认尝试解析关键字段）

说明：基本面数据通常需要相应订阅；paper/无订阅时会返回错误，脚本会提示。
"""
import argparse
import sys
import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))
from common import (
    connect, safe_disconnect, parse_contract, qualify,
    print_result, attach_error_collector, _fail,
)

_REPORT_MAP = {
    "snapshot": "ReportSnapshot",
    "finsummary": "ReportsFinSummary",
    "ratios": "ReportRatios",
    "statements": "ReportsFinStatements",
    "calendar": "CalendarReport",
}


def _parse_snapshot(xml):
    """从 ReportSnapshot XML 抽取若干关键字段，best-effort。"""
    import xml.etree.ElementTree as ET
    out = {}
    try:
        root = ET.fromstring(xml)
        co = root.find(".//CoIDs")
        if co is not None:
            for cid in co.findall("CoID"):
                t = cid.get("Type")
                if t in ("CompanyName",):
                    out["company"] = cid.text
        info = root.find(".//CoGeneralInfo")
        if info is not None:
            emp = info.find("Employees")
            if emp is not None:
                out["employees"] = emp.text
        # 行业
        for ind in root.findall(".//Industry"):
            if ind.get("type") == "TRBC":
                out["industry"] = ind.text
                break
        # 关键比率
        ratios = {}
        for r in root.findall(".//Ratio"):
            fid = r.get("FieldName")
            if fid and r.text:
                ratios[fid] = r.text
        for k in ("MKTCAP", "TTMPR2REV", "PEEXCLXOR", "PRICE2BK", "TTMDIVSHR"):
            if k in ratios:
                out[k] = ratios[k]
        # 业务简介：ReportSnapshot 里在 <TextInfo><Text Type="Business Summary">
        biz = None
        for txt in root.findall(".//TextInfo/Text"):
            if (txt.get("Type") or "").lower() == "business summary" and txt.text:
                biz = txt.text
                break
        if biz is None:  # 回退：第一个非空 Text
            for txt in root.findall(".//Text"):
                if txt.text and txt.text.strip():
                    biz = txt.text
                    break
        if biz:
            out["business"] = biz.strip()[:400]
    except Exception:
        pass
    return out


def get_fundamentals(spec, report="snapshot", raw=False, output_json=False):
    ib = None
    try:
        report_type = _REPORT_MAP.get(report.lower())
        if not report_type:
            _fail(f"未知 report 类型: {report}，可选 {', '.join(_REPORT_MAP)}", output_json)
        ib = connect(readonly=True)
        errors = attach_error_collector(ib)
        qc = qualify(ib, parse_contract(spec), output_json)

        xml = ib.reqFundamentalData(qc, report_type)
        if not xml:
            msg = f"未取到 {spec} 的基本面数据（{report_type}）"
            if errors:
                msg += "：" + "; ".join(e.get("hint") or e["msg"] for e in errors)
            msg += "。基本面数据通常需要相应订阅。"
            _fail(msg, output_json)

        result = {"symbol": qc.symbol, "report": report_type, "length": len(xml)}
        if raw or report_type != "ReportSnapshot":
            result["xml"] = xml
        else:
            result["fields"] = _parse_snapshot(xml)
        print_result(result, output_json, _print_text)
    except SystemExit:
        raise
    except Exception as e:
        _fail(str(e), output_json)
    finally:
        safe_disconnect(ib)


def _print_text(result):
    print("=" * 70)
    print(f"基本面  {result['symbol']}  ({result['report']})")
    print("=" * 70)
    if "fields" in result:
        f = result["fields"]
        if not f:
            print("  （未能解析出结构化字段，可加 --raw 看原始 XML）")
        for k, label in [("company", "公司"), ("industry", "行业"), ("employees", "员工数"),
                         ("MKTCAP", "市值"), ("PEEXCLXOR", "市盈率"), ("PRICE2BK", "市净率"),
                         ("TTMPR2REV", "市销率"), ("TTMDIVSHR", "每股股息")]:
            if k in f:
                print(f"  {label}: {f[k]}")
        if f.get("business"):
            print(f"\n  业务: {f['business']}")
    else:
        print(f"  原始 XML 长度 {result['length']} 字符（已置于 JSON 的 xml 字段 / 用 --json 获取）")
    print("=" * 70)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="基本面/公司信息")
    p.add_argument("spec", help="标的代码，如 AAPL / HK.700")
    p.add_argument("--report", default="snapshot", help="snapshot/finsummary/ratios/statements/calendar")
    p.add_argument("--raw", action="store_true", help="输出原始 XML")
    p.add_argument("--json", action="store_true", dest="output_json", help="输出 JSON 格式")
    args = p.parse_args()
    get_fundamentals(args.spec, args.report, args.raw, args.output_json)
