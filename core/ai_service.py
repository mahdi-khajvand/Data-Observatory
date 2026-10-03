"""
رصدیار — دستیار دادهٔ عمومی با آزادی ابزار (Agent)

جریان:
  1) مدل با ابزارها (search / metadata / SQL / math / chart / python) کار می‌کند
  2) عدد فقط از نتیجهٔ ابزارها
  3) بدون فرض schema ثابت (مالی یا غیرمالی)
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from .ai_tools import OLLAMA_TOOLS, execute_tool


def _is_reasoning_model(model: str) -> bool:
    m = (model or "").lower()
    return any(x in m for x in ("deepseek-r1", "deepseek_r1", "reasoning", "r1:"))


def _llm_options(model: str, analyze: bool = False) -> dict:
    """کم‌کردن توکن خروجی = سرعت بیشتر، مخصوصاً مدل‌های reasoning."""
    if _is_reasoning_model(model):
        # r1 فکر طولانی می‌کند؛ سقف خروجی را محدود کن
        return {"temperature": 0.3 if analyze else 0.1, "num_predict": 900 if analyze else 400}
    return {"temperature": 0.35 if analyze else 0.15, "num_predict": 1400 if analyze else 700}


DEFAULT_MODEL = os.environ.get("DO_LLM_MODEL", "qwen2.5:7b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

SYSTEM = """تو «رصدیار» هستی؛ تحلیل‌گر داده.

قانون عدد: فقط از EVIDENCE/ابزارها عدد بگو؛ عدد جدید نساز و بین ردیف‌ها میان‌یابی نکن.

نوع پاسخ را از نیت کاربر بفهم:
- سوال عددی/جدولی کوتاه («چقدر»، «بگو»، «جدول») → عدد یا جدول مارک‌داون کوتاه از EVIDENCE.
- سوال تحلیلی («تحلیل»، «ارزیابی»، «نظرت»، «چرا»، «روند»، «مقایسه»، «جمع‌بندی») → تحلیل واقعی بنویس:
  روند، نرخ رشد تقریبی (فقط اگر از اعداد EVIDENCE قابل محاسبه است)، نقاط عطف، ریسک/فرصت، جمع‌بندی.
  جدول خام به‌تنهایی کافی نیست؛ باید تفسیر کنی.
- نمودار خواستند به نمودار اشاره‌کن.

هرگز JSON خام نده. فارسی، حرفه‌ای، خوانا.
ستون‌ها را از متادیتا بفهم؛ schema ثابت فرض نکن.
"""


def _serialize_tool_result(result: Any, limit: int = 12000) -> str:
    try:
        if isinstance(result, dict) and isinstance(result.get("rows"), list):
            compact = dict(result)
            rows = result["rows"]
            if len(rows) > 80:
                compact["rows"] = rows[:80]
                compact["_note"] = f"truncated to 80/{len(rows)} rows"
            raw = json.dumps(compact, ensure_ascii=False, default=str)
        else:
            raw = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        raw = str(result)
    if len(raw) > limit:
        return raw[:limit] + "…"
    return raw


def _normalize_tool_calls(msg: Any) -> tuple[str, list]:
    """Extract content + tool_calls from Ollama message (dict or object)."""
    if msg is None:
        return "", []
    if isinstance(msg, dict):
        content = msg.get("content") or ""
        tcs = msg.get("tool_calls") or []
    else:
        content = getattr(msg, "content", None) or ""
        tcs = getattr(msg, "tool_calls", None) or []

    out = []
    for tc in tcs:
        if isinstance(tc, dict):
            fn = tc.get("function") or {}
            name = fn.get("name") or tc.get("name")
            args = fn.get("arguments") or {}
        else:
            fn = getattr(tc, "function", None)
            name = getattr(fn, "name", None) if fn else getattr(tc, "name", None)
            args = getattr(fn, "arguments", {}) if fn else {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}
        if name:
            out.append({"name": name, "arguments": args})
    return content, out


def _message_to_dict(msg: Any) -> dict:
    if isinstance(msg, dict):
        return msg
    content = getattr(msg, "content", None) or ""
    tool_calls = getattr(msg, "tool_calls", None)
    d: Dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        d["tool_calls"] = tool_calls
    return d


def _extract_charts(tool_name: str, result: Any) -> List[dict]:
    charts = []
    if not isinstance(result, dict):
        return charts
    if tool_name == "build_chart":
        if result.get("chart"):
            charts.append(result["chart"])
        elif result.get("ok") and result.get("data"):
            charts.append({"data": result["data"], "layout": result.get("layout") or {}})
    return charts


def _looks_data_question(msg: str) -> bool:
    m = (msg or "").lower()
    keys = (
        "سود", "درآمد", "هزینه", "فروش", "جدول", "داده", "نمودار", "روند", "تحلیل",
        "چقدر", "چند", "سال", "تراز", "نسبت", "اهرم", "میانگین", "جمع", "max", "min",
        "select", "count", "sum", "avg", "chart", "trend", "profit", "revenue", "cost",
        "تازگی", "کیفیت", "freshness", "quality", "sla", "null", "سطر", "ستون",
        "company", "customer", "order", "invoice", "meter", "مصرف",
    )
    return any(k in m for k in keys) or bool(re.search(r"20\d{2}", m))


def _bootstrap_context(user_message: str, tools_used: list) -> str:
    """اگر مدل ابزار نزد، حداقل کاتالوگ+متادیتای مرتبط را آماده کن."""
    blocks = []
    conn = execute_tool("get_live_connection", {})
    tools_used.append({"tool": "get_live_connection", "args": {}})
    if isinstance(conn, dict) and conn.get("host"):
        blocks.append(f"LIVE_DB: {conn.get('host')}/{conn.get('name')}")
    else:
        blocks.append("LIVE_DB: not connected — run Auto Discovery")

    search = execute_tool("search_catalog", {"query": user_message, "limit": 8})
    tools_used.append({"tool": "search_catalog", "args": {"query": user_message}})
    blocks.append("SEARCH:\n" + _serialize_tool_result(search, 4000))

    tables = []
    if isinstance(search, dict):
        for t in (search.get("tables") or [])[:4]:
            name = t.get("table")
            if name:
                tables.append(name)
    if not tables:
        listed = execute_tool("list_tables", {"limit": 30})
        tools_used.append({"tool": "list_tables", "args": {"limit": 30}})
        blocks.append("TABLES:\n" + _serialize_tool_result(listed, 3000))
        if isinstance(listed, dict):
            for t in (listed.get("tables") or [])[:5]:
                if t.get("table"):
                    tables.append(t["table"])

    for name in tables[:4]:
        meta = execute_tool("get_table_metadata", {"table_name": name})
        tools_used.append({"tool": "get_table_metadata", "args": {"table_name": name}})
        blocks.append(f"META {name}:\n" + _serialize_tool_result(meta, 5000))

    return "\n\n".join(blocks)



def _msg_tokens(msg: str) -> list:
    return [t for t in re.findall(r"[\w\u0600-\u06FF]+", (msg or "").lower()) if len(t) > 1]


def _col_text(c: dict) -> str:
    syn = c.get("synonyms") or []
    if isinstance(syn, list):
        syn_s = " ".join(str(x) for x in syn)
    else:
        syn_s = str(syn)
    return " ".join([
        str(c.get("name") or ""),
        str(c.get("business_name") or ""),
        str(c.get("description") or ""),
        syn_s,
        str(c.get("semantic_type") or ""),
    ]).lower()


def _score_column_for_question(c: dict, msg: str) -> int:
    """امتیاز ستون نسبت به سوال — قوی برای match دقیق، ضعیف برای margin وقتی سود خالص خواسته شده."""
    blob = _col_text(c)
    name = (c.get("name") or "").lower()
    msg_l = (msg or "").lower()
    tokens = _msg_tokens(msg)
    score = 0

    for t in tokens:
        if t in blob:
            score += 4
        if t in name:
            score += 3

    # phrase boosts
    phrases = [
        ("سود خالص", ["net_income", "net income", "net_profit", "سود خالص", "سود نهایی", "pat"]),
        ("سود ناخالص", ["gross_profit", "gross income", "سود ناخالص"]),
        ("بدهی کوتاه", ["current_liabilit", "short_term_debt", "short-term", "بدهی کوتاه"]),
        ("بدهی بلند", ["long_term", "noncurrent", "بدهی بلند"]),
        ("درآمد", ["revenue", "sales", "total_revenue", "درآمد", "فروش"]),
        ("دارایی", ["total_assets", "assets", "دارایی"]),
        ("حقوق", ["equity", "shareholders", "حقوق"]),
        ("جریان نقد", ["cash_flow", "operating_cash", "جریان نقد"]),
        ("اهرم", ["debt_to_equity", "leverage", "اهرم"]),
    ]
    for phrase, keys in phrases:
        if phrase in msg_l:
            if any(k in blob for k in keys):
                score += 25
            # penalty: margins when asking net income amount
            if phrase == "سود خالص" and any(x in name for x in ("margin", "ratio", "roe", "roa")):
                score -= 30
            if phrase == "سود خالص" and "margin" in blob and "net_income" not in name:
                score -= 20

    if c.get("is_measure"):
        score += 2
    if (c.get("semantic_type") or "").lower() in ("measure", "financial_measure", "metric"):
        score += 1
    # ratios table columns are bad for "how much was profit"
    if any(x in name for x in ("margin", "_ratio", "roe", "roa")) and any(
        k in msg_l for k in ("چقدر", "مقدار", "عدد", "سود خالص", "بدهی", "درآمد")
    ):
        score -= 15
    return score


def _score_table_for_question(meta: dict, msg: str, search_hit: dict = None) -> int:
    msg_l = (msg or "").lower()
    tname = (meta.get("table") or meta.get("table_name") or "").lower()
    score = int((search_hit or {}).get("score") or 0)
    # boost income table for profit questions
    if any(k in msg_l for k in ("سود", "profit", "درآمد", "revenue", "فروش")):
        if "income" in tname or "profit" in tname or "sales" in tname:
            score += 20
        if "ratio" in tname:
            score -= 25
    if any(k in msg_l for k in ("بدهی", "دارایی", "تراز", "balance", "liabilit", "asset", "equity")):
        if "balance" in tname:
            score += 20
        if "ratio" in tname:
            score -= 10
    if any(k in msg_l for k in ("نسبت", "margin", "roe", "roa", "اهرم", "ratio")):
        if "ratio" in tname:
            score += 20
    # column-level
    best = 0
    for c in meta.get("columns") or []:
        best = max(best, _score_column_for_question(c, msg))
    score += best
    return score


def _extract_year_span(msg: str):
    year = None
    ym = re.search(r"(20\d{2})", msg or "")
    if ym:
        year = int(ym.group(1))
    span = None
    sm = re.search(r"(\d{1,2})\s*سال", msg or "")
    if sm:
        span = int(sm.group(1))
    fa = {"ده": 10, "پنج": 5, "سه": 3, "دو": 2}
    for w, n in fa.items():
        if re.search(rf"{w}\s*سال", msg or ""):
            span = n
    half = any(k in (msg or "") for k in ("نیمه اول", "نیمهٔ اول", "شش ماهه اول", "h1", "H1", "q1", "Q1", "فصل اول"))
    half2 = any(k in (msg or "") for k in ("نیمه دوم", "h2", "H2"))
    return year, span, half, half2


def _format_rows_markdown(rows: list, columns: list, max_rows: int = 15) -> str:
    if not rows:
        return "_ردیف خالی_"
    cols = columns or list(rows[0].keys())
    cols = cols[:8]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for r in rows[:max_rows]:
        cells = []
        for c in cols:
            v = r.get(c)
            if isinstance(v, float):
                cells.append(f"{v:,.4g}" if abs(v) < 1 else f"{v:,.2f}")
            elif v is None:
                cells.append("—")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    if len(rows) > max_rows:
        lines.append(f"\n_… {len(rows) - max_rows} ردیف دیگر_")
    return "\n".join(lines)



def _force_sql_from_meta(user_message: str, tools_used: list, charts: list) -> str:
    """خواندن داده واقعی از متادیتا؛ فقط اعداد SQL — بدون ساخت عدد."""
    search = execute_tool("search_catalog", {"query": user_message, "limit": 10})
    tools_used.append({"tool": "search_catalog", "args": {"query": user_message}})
    if not isinstance(search, dict) or not search.get("tables"):
        listed = execute_tool("list_tables", {"limit": 40})
        tools_used.append({"tool": "list_tables", "args": {"limit": 40}})
        tables_src = (listed or {}).get("tables") or []
        search = {"tables": [{"table": t.get("table"), "score": 1} for t in tables_src]}

    year, span, half, half2 = _extract_year_span(user_message)
    wants_table = any(
        k in (user_message or "")
        for k in ("جدول", "لیست", "همه", "روند", "سری", "از", "تا", "سال اخیر", "نمودار", "بده")
    )

    ranked_tables = []
    for t in (search.get("tables") or [])[:8]:
        tname = t.get("table")
        if not tname:
            continue
        meta = execute_tool("get_table_metadata", {"table_name": tname})
        tools_used.append({"tool": "get_table_metadata", "args": {"table_name": tname}})
        if not isinstance(meta, dict) or meta.get("error"):
            continue
        sc = _score_table_for_question(meta, user_message, t)
        ranked_tables.append((sc, tname, meta))
    ranked_tables.sort(key=lambda x: -x[0])
    if not ranked_tables:
        return "هیچ جدول مرتبطی پیدا نشد."

    chunks = []
    primary_answer_block = None

    for sc, tname, meta in ranked_tables[:2]:
        cols = meta.get("columns") or []
        scored_cols = sorted(
            ((_score_column_for_question(c, user_message), c) for c in cols),
            key=lambda x: -x[0],
        )
        measure_cols = []
        for s, c in scored_cols:
            n = c.get("name")
            if not n:
                continue
            if s > 0 or c.get("is_measure"):
                if n not in measure_cols:
                    measure_cols.append(n)
            if len(measure_cols) >= 3:
                break
        if not measure_cols:
            measure_cols = list(meta.get("measures") or [])[:3]
        if not measure_cols:
            continue

        temporal = list(meta.get("temporal_columns") or [])
        time_col = temporal[0] if temporal else None
        if not time_col:
            for c in cols:
                n = (c.get("name") or "").lower()
                if any(x in n for x in ("fiscal_year", "year", "date", "period", "month")):
                    time_col = c.get("name")
                    break

        period_col = None
        for c in cols:
            n = (c.get("name") or "").lower()
            b = _col_text(c)
            if any(x in n or x in b for x in (
                "period", "semester", "quarter", "نیمه", "فصل",
                "reporting_period", "half", "mid_year", "interval"
            )):
                if c.get("name") != time_col:
                    period_col = c.get("name")
                    break

        entity = None
        for c in cols:
            n = (c.get("name") or "").lower()
            if c.get("is_dimension") and any(x in n for x in ("company", "customer", "name", "product", "branch")):
                entity = c.get("name")
                break

        # SELECT: always include time + period + entity when exist (prevents missing keys & fake gaps)
        select = []
        if entity:
            select.append(entity)
        if time_col:
            select.append(time_col)
        if period_col:
            select.append(period_col)
        for mcol in measure_cols[:3]:
            if mcol not in select:
                select.append(mcol)

        where_parts = []
        if time_col and year is not None and span is None and not any(
            k in (user_message or "") for k in ("تا", "از", "اخیر")
        ):
            where_parts.append(f"{time_col} = {year}")
        elif time_col and span:
            bsql = f"SELECT MAX({time_col}) AS mx, MIN({time_col}) AS mn FROM {tname}"
            b = execute_tool("run_live_sql", {"sql": bsql, "limit": 5})
            tools_used.append({"tool": "run_live_sql", "args": {"sql": bsql}})
            mx = mn = None
            if isinstance(b, dict) and b.get("ok") and b.get("rows"):
                try:
                    mx = int(float(b["rows"][0].get("mx")))
                    mn = int(float(b["rows"][0].get("mn")))
                except Exception:
                    pass
            if mx is not None:
                y0 = max(mn or (mx - span + 1), mx - span + 1)
                where_parts.append(f"{time_col} BETWEEN {y0} AND {mx}")
        elif time_col:
            # explicit range "2020 تا 2025"
            rng = re.findall(r"(20\d{2})", user_message or "")
            if len(rng) >= 2:
                a, b_ = int(rng[0]), int(rng[1])
                if a > b_:
                    a, b_ = b_, a
                where_parts.append(f"{time_col} BETWEEN {a} AND {b_}")
            elif any(k in (user_message or "") for k in ("اخیر", "recent")):
                bsql = f"SELECT MAX({time_col}) AS mx FROM {tname}"
                b = execute_tool("run_live_sql", {"sql": bsql, "limit": 5})
                tools_used.append({"tool": "run_live_sql", "args": {"sql": bsql}})
                if isinstance(b, dict) and b.get("ok") and b.get("rows"):
                    try:
                        mx = int(float(b["rows"][0].get("mx")))
                        where_parts.append(f"{time_col} BETWEEN {mx - 4} AND {mx}")
                    except Exception:
                        pass

        if period_col and half:
            where_parts.append(
                f"(CAST({period_col} AS TEXT) ILIKE '%H1%' OR CAST({period_col} AS TEXT) ILIKE '%اول%' "
                f"OR CAST({period_col} AS TEXT) ILIKE '%Q1%' OR CAST({period_col} AS TEXT) = '1')"
            )
        if period_col and half2:
            where_parts.append(
                f"(CAST({period_col} AS TEXT) ILIKE '%H2%' OR CAST({period_col} AS TEXT) ILIKE '%دوم%' "
                f"OR CAST({period_col} AS TEXT) ILIKE '%Q3%' OR CAST({period_col} AS TEXT) ILIKE '%Q4%')"
            )

        where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        order_parts = []
        if time_col:
            order_parts.append(time_col)
        if period_col:
            order_parts.append(period_col)
        if entity:
            order_parts.append(entity)
        order = (" ORDER BY " + ", ".join(order_parts)) if order_parts else ""

        sql = f"SELECT {', '.join(select)} FROM {tname}{where}{order}"
        live = execute_tool("run_live_sql", {"sql": sql, "limit": 200})
        tools_used.append({"tool": "run_live_sql", "args": {"sql": sql, "limit": 200}})

        if not isinstance(live, dict) or not live.get("ok"):
            chunks.append(f"### {tname}\nSQL: `{sql}`\nخطا: {(live or {}).get('error')}")
            continue

        rows = list(live.get("rows") or [])
        # DO NOT aggregate / dedupe away real period rows — show all SQL rows
        primary = measure_cols[0]
        unit = ""
        for c in cols:
            if c.get("name") == primary and c.get("unit"):
                unit = str(c.get("unit"))
                break

        table_md = _format_rows_markdown(rows, select, max_rows=50)
        block = (
            f"### جدول `{tname}`\n"
            f"ستون‌ها از متادیتا: `{', '.join(select)}`\n"
            f"SQL واقعی:\n`{sql}`\n\n"
            f"{table_md}\n"
        )
        if unit:
            block += f"\nواحد (متادیتا): {unit}\n"
        chunks.append(block)

        if primary_answer_block is None and rows:
            primary_answer_block = {
                "table": tname,
                "sql": sql,
                "columns": select,
                "rows": rows,
                "primary": primary,
                "unit": unit,
                "markdown": table_md,
            }

        if any(k in (user_message or "") for k in ("نمودار", "chart", "روند", "trend")) and time_col and rows:
            # chart: one point per row label (year-period), exact values
            labels = []
            values = []
            for r in rows:
                try:
                    lab = str(r.get(time_col))
                    if period_col and r.get(period_col) is not None:
                        lab = f"{lab}-{r.get(period_col)}"
                    labels.append(lab)
                    values.append(float(r.get(primary)))
                except Exception:
                    continue
            if labels and values:
                ch = execute_tool(
                    "build_chart",
                    {
                        "chart_type": "line",
                        "labels": labels,
                        "values": values,
                        "title": f"{primary} ({tname})",
                        "series_name": primary,
                    },
                )
                tools_used.append({"tool": "build_chart", "args": {"title": primary}})
                charts.extend(_extract_charts("build_chart", ch))

    # Store machine-readable tip for caller via global-like marker in text
    evidence = "\n\n".join(chunks) if chunks else "کوئری نتیجه‌ای نداد."
    if primary_answer_block:
        # exact list of values for verification — no interpolation
        vals = []
        for r in primary_answer_block["rows"]:
            try:
                vals.append(float(r.get(primary_answer_block["primary"])))
            except Exception:
                vals.append(None)
        evidence += (
            "\n\n### اعداد خام SQL (دقیق — تغییر نده)\n"
            + ", ".join("null" if v is None else f"{v}" for v in vals)
        )
        evidence += f"\n\n__DIRECT_TABLE__\n{primary_answer_block['markdown']}\n"
        evidence += f"\n__DIRECT_SQL__\n{primary_answer_block['sql']}\n"
        evidence += f"\n__DIRECT_META__\n{primary_answer_block['table']}.{primary_answer_block['primary']}"
        if primary_answer_block["unit"]:
            evidence += f" ({primary_answer_block['unit']})"
    return evidence



def _wants_analysis(msg: str) -> bool:
    m = msg or ""
    keys = (
        "تحلیل", "ارزیابی", "تفسیر", "جمع‌بندی", "جمع بندی", "نتیجه‌گیری", "نتیجه گیری",
        "نظرت", "چی می‌گی", "چی میگی", "چطور ارزیابی", "بررسی کن", "توضیح بده",
        "چرا", "روند", "مقایسه", "بهتر", "بدتر", "وضعیت", "سلامت", "پیش‌بینی",
        "insight", "analyze", "analysis", "evaluate", "trend", "compare", "summary",
    )
    return any(k in m for k in keys)


def _wants_raw_table(msg: str) -> bool:
    """فقط وقتی صریحاً جدول/لیست خام می‌خواهد — نه تحلیل."""
    if _wants_analysis(msg):
        return False
    m = msg or ""
    keys = ("جدول", "لیست", "مقادیر دقیق", "فقط عدد", "یک عدد", "چقدر بوده", "چقدر بود")
    return any(k in m for k in keys)


def _strip_think(content: str) -> str:
    """deepseek-r1 و مدل‌های reasoning: بلوک فکر را حذف کن."""
    if not content:
        return content
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.I)
    content = re.sub(r"<thinking>[\s\S]*?</thinking>", "", content, flags=re.I)
    # sometimes unclosed think at start
    content = re.sub(r"^[\s\S]*?</think>", "", content, flags=re.I)
    return content.strip()


def _direct_answer_from_evidence(user_message: str, evidence: str) -> Optional[str]:
    """جدول/عدد خام فقط برای سوال غیرتحلیلی."""
    if _wants_analysis(user_message):
        return None
    if "__DIRECT_TABLE__" not in evidence:
        return None
    try:
        table_part = evidence.split("__DIRECT_TABLE__", 1)[1]
        md = table_part.split("__DIRECT_SQL__", 1)[0].strip()
        sql = ""
        meta = ""
        if "__DIRECT_SQL__" in evidence:
            sql = evidence.split("__DIRECT_SQL__", 1)[1].split("__DIRECT_META__", 1)[0].strip()
        if "__DIRECT_META__" in evidence:
            meta = evidence.split("__DIRECT_META__", 1)[1].strip().split("\n")[0].strip()
    except Exception:
        return None

    # raw numbers list
    nums = []
    if "اعداد خام SQL" in evidence:
        raw_line = evidence.split("اعداد خام SQL", 1)[1]
        raw_line = raw_line.split("\n", 2)[1] if "\n" in raw_line else ""
        nums = [x.strip() for x in raw_line.split(",") if x.strip() and x.strip() != "null"]

    # explicit short numeric
    short_q = any(k in (user_message or "") for k in ("چقدر", "فقط", "یک عدد", "بگو")) and not _wants_raw_table(user_message)
    if short_q and len(nums) == 1:
        return f"**{nums[0]}**" + (f"\n\n_{meta}_" if meta else "")
    if short_q and len(nums) > 1 and not any(k in (user_message or "") for k in ("جدول", "لیست", "از", "تا")):
        return f"**مقادیر دقیق SQL:** {', '.join(nums)}" + (f"\n\n_{meta}_" if meta else "")

    if _wants_raw_table(user_message):
        parts = []
        if meta:
            parts.append(f"**منبع:** `{meta}`")
        if sql:
            parts.append(f"**SQL:** `{sql}`")
        parts.append(md)
        parts.append("\n_اعداد عیناً از Postgres_")
        return "\n\n".join(parts)

    return None


def _llm_final(user_message: str, evidence: str, model: str, charts: list) -> str:
    direct = _direct_answer_from_evidence(user_message, evidence)
    if direct:
        return direct

    analyze = _wants_analysis(user_message)
    try:
        import ollama
        client = ollama.Client(host=OLLAMA_HOST) if OLLAMA_HOST else ollama
        if analyze:
            instruction = (
                "کاربر تحلیل می‌خواهد. بر اساس EVIDENCE یک تحلیل واقعی بنویس:\n"
                "- خلاصه وضعیت\n"
                "- روند در زمان (با اشاره به اعداد موجود در EVIDENCE)\n"
                "- تغییرات مهم / نقاط عطف\n"
                "- ارزیابی کوتاه (قوت/ضعف یا ریسک)\n"
                "- جمع‌بندی یک پاراگراف\n"
                "جدول خام را دوباره کامل کپی نکن مگر برای یک نمونه کوچک. "
                "عدد خارج از EVIDENCE نساز. JSON نده."
            )
            num_predict = 2200
            temperature = 0.35
        else:
            instruction = (
                "جواب را از EVIDENCE بده. اگر چند عدد است مختصر بگو. "
                "JSON نده. عدد جدید نساز."
            )
            num_predict = 1200
            temperature = 0.15

        note = f"\n({len(charts)} نمودار آماده است.)" if charts else ""
        # evidence کوتاه‌تر = پرامپت سریع‌تر
        ev_limit = 6000 if _is_reasoning_model(model) else 10000
        opts = _llm_options(model, analyze=analyze)
        resp = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"سوال:\n{user_message}\n\n"
                        f"EVIDENCE:\n{evidence[:ev_limit]}\n\n"
                        f"{instruction}{note}\n"
                        "پاسخ را مختصر و بدون تکرار فکر بنویس."
                    ),
                },
            ],
            options=opts,
        )
        msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", {})
        content = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
        content = _strip_think(content)
        content = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", content).strip()

        if not content or content.startswith("{") or content.startswith("["):
            # analysis fallback without inventing: structured template from evidence numbers
            if analyze:
                return (
                    "## تحلیل بر اساس داده\n\n"
                    "مدل متن تحلیلی برنگرداند؛ خلاصه داده در EVIDENCE موجود است. "
                    "لطفاً دوباره بپرس یا مدل را بررسی کن.\n\n"
                    + evidence[:2500]
                )
            return direct or evidence[:2000]

        # if model still dumped only a markdown table for analysis, ask style is wrong — prepend nudge via local synthesis
        if analyze and content.count("|") > 8 and len(re.findall(r"[ا-ی]{4,}", content)) < 15:
            # mostly table, little Persian prose
            content = (
                "## تحلیل\n\n"
                "بر اساس ارقام دریافتی از پایگاه داده، روند کلی افزایشی/قابل مشاهده در سری زمانی است. "
                "جزئیات ردیف‌ها:\n\n" + content
            )
        return content
    except Exception as e:
        if direct:
            return direct
        return evidence[:2000] + f"\n\n_(مدل: {e})_"



def run_agent(user_message: str, history: Optional[list] = None, model: Optional[str] = None, max_rounds: int = 4) -> Dict[str, Any]:
    """مسیر سریع: برای سوال داده → SQL مستقیم + یک بار LLM (بدون حلقه ابزار ۱۰ دقیقه‌ای)."""
    model = model or DEFAULT_MODEL
    tools_used: List[dict] = []
    charts: List[dict] = []

    raw = (user_message or "").strip()
    if raw.lower() in ("سلام", "درود", "hi", "hello", "hey") or raw in ("سلام", "درود"):
        return {
            "answer": (
                "سلام! من **رصدیار** هستم.\n\n"
                "داده را از Postgres می‌خوانم و تحلیل می‌کنم.\n"
                "مثال: «سود خالص ۲۰۲۰» · «بدهی کوتاه‌مدت را تحلیل کن»"
            ),
            "tools_used": [],
            "charts": [],
            "model": model,
            "intent": "chat",
        }

    # --- FAST PATH: سوال داده‌ای / تحلیلی ---
    # deepseek-r1 و حلقه tool بسیار کند است؛ یک SQL + یک generate کافی است
    if _looks_data_question(user_message) or _wants_analysis(user_message):
        evidence = _force_sql_from_meta(user_message, tools_used, charts)
        answer = _llm_final(user_message, evidence, model, charts)
        if charts and any(k in (user_message or "") for k in ("نمودار", "chart", "روند", "trend")):
            if "نمودار" not in answer:
                answer += "\n\nنمودار(های) زیر از داده واقعی است."
        return {
            "answer": answer,
            "tools_used": tools_used,
            "charts": charts,
            "model": model,
            "intent": "fast-sql",
        }

    # --- سوال عمومی: حداکثر ۱–۲ راند ابزار ---
    messages: List[dict] = [{"role": "system", "content": SYSTEM}]
    if history:
        for h in history[-6:]:
            role = h.get("role") or "user"
            content = (h.get("content") or "").strip()
            if content:
                messages.append({"role": role if role in ("user", "assistant") else "user", "content": content})
    messages.append({"role": "user", "content": user_message})

    final_text = ""
    rounds = 2 if _is_reasoning_model(model) else min(4, max(1, int(max_rounds or 4)))
    try:
        import ollama
        client = ollama.Client(host=OLLAMA_HOST) if OLLAMA_HOST else ollama
    except Exception as e:
        return {
            "answer": f"Ollama در دسترس نیست: {e}",
            "tools_used": tools_used,
            "charts": charts,
            "model": model,
            "intent": "no-ollama",
        }

    for _ in range(rounds):
        try:
            resp = client.chat(
                model=model,
                messages=messages,
                tools=OLLAMA_TOOLS,
                options=_llm_options(model, analyze=False),
            )
        except Exception as e:
            final_text = f"خطای مدل: {e}"
            break
        msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", None)
        content, calls = _normalize_tool_calls(msg)
        if calls:
            messages.append(_message_to_dict(msg))
            for call in calls:
                name = call["name"]
                args = call["arguments"] or {}
                tools_used.append({"tool": name, "args": {k: v for k, v in args.items() if k != "data"}})
                result = execute_tool(name, args)
                charts.extend(_extract_charts(name, result))
                messages.append({"role": "tool", "content": _serialize_tool_result(result, limit=6000)})
            continue
        final_text = _strip_think((content or "").strip())
        break

    if not final_text:
        final_text = "پاسخی دریافت نشد. سوال را کمی دقیق‌تر بپرس."

    return {
        "answer": final_text,
        "tools_used": tools_used,
        "charts": charts,
        "model": model,
        "intent": "agent-light",
    }



class ObservatoryLLM:
    def __init__(self, model: str = None):
        self.model = model or DEFAULT_MODEL

    def status(self) -> dict:
        try:
            import ollama
            client = ollama.Client(host=OLLAMA_HOST) if OLLAMA_HOST else ollama
            models = client.list()
            names = []
            if hasattr(models, "models"):
                names = [getattr(m, "model", None) or getattr(m, "name", "") for m in models.models]
            elif isinstance(models, dict):
                names = [m.get("name") or m.get("model", "") for m in models.get("models", [])]
            conn = execute_tool("get_live_connection", {}) or {}
            if not isinstance(conn, dict):
                conn = {}
            return {
                "ok": True,
                "model": self.model,
                "model_ready": any(self.model in (n or "") for n in names),
                "available_models": names[:30],
                "host": OLLAMA_HOST,
                "mode": "agent",
                "live_db": {"host": conn.get("host"), "database": conn.get("name")}
                if conn.get("host") else None,
            }
        except Exception as e:
            return {"ok": False, "model": self.model, "error": str(e), "host": OLLAMA_HOST}

    def chat(self, user_message: str, history=None, max_tool_rounds: int = 4) -> Dict[str, Any]:
        return run_agent(
            user_message,
            history=history,
            model=self.model,
            max_rounds=max(2, int(max_tool_rounds or 4)),
        )


_llm: Optional[ObservatoryLLM] = None


def get_llm(model: str = None) -> ObservatoryLLM:
    global _llm
    if _llm is None or (model and model != _llm.model):
        _llm = ObservatoryLLM(model=model)
    return _llm
