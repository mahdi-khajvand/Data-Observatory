"""
ابزارهای دستیار رصدیار — عمومی برای هر نوع داده
منابع:
  CATALOG / METADATA  → جداول و ستون‌ها با متادیتای غنی
  LIVE SQL            → Postgres کشف‌شده
  META SQL            → SQLite داخلی Observatory
  FRESHNESS / QUALITY → تازگی و کیفیت
  MATH / CHART / PY   → محاسبه و نمودار
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional

from . import store, services


def _split_list(val: Optional[str]) -> list:
    if not val:
        return []
    s = str(val).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
    return [x.strip() for x in s.replace(";", ",").split(",") if x.strip()]


def _infer_from_name(name: str, dtype: str = "") -> dict:
    """حدس معنا از نام ستون وقتی متادیتا خالی است — عمومی، نه فقط مالی."""
    low = (name or "").lower()
    dt = (dtype or "").lower()
    out = {
        "business_name": (name or "").replace("_", " ").title(),
        "semantic_type": "",
        "unit": "",
        "is_measure": False,
        "is_dimension": False,
        "guessed": True,
    }
    measure_hints = (
        "amount", "price", "cost", "qty", "quantity", "total", "sum", "avg", "mean",
        "count", "rate", "ratio", "score", "value", "volume", "weight", "size",
        "profit", "revenue", "income", "expense", "sales", "balance", "power",
        "energy", "voltage", "current", "demand", "consumption", "kwh", "duration",
        "latency", "سود", "درآمد", "هزینه", "مقدار", "تعداد", "نرخ", "میانگین",
    )
    time_hints = (
        "time", "date", "year", "month", "day", "week", "hour", "timestamp",
        "created", "updated", "period", "fiscal", "سال", "ماه", "روز", "تاریخ", "دوره",
    )
    dim_hints = (
        "id", "code", "status", "type", "category", "region", "zone", "name",
        "city", "country", "branch", "company", "customer", "product", "user",
        "شرکت", "مشتری", "محصول", "وضعیت", "نوع", "دسته",
    )
    if any(x in low for x in measure_hints):
        out["is_measure"] = True
        out["semantic_type"] = "measure"
    if any(x in low for x in time_hints):
        out["semantic_type"] = "temporal"
        out["is_dimension"] = True
        out["is_measure"] = False
    if any(x in low for x in dim_hints) and not out["is_measure"]:
        out["semantic_type"] = out["semantic_type"] or ("identifier" if "id" in low else "categorical")
        out["is_dimension"] = True
    if any(x in dt for x in ("int", "numeric", "double", "float", "decimal", "real", "number")):
        if not out["semantic_type"]:
            out["semantic_type"] = "numeric"
            out["is_measure"] = True
    if any(x in dt for x in ("date", "time", "timestamp")):
        out["semantic_type"] = "temporal"
        out["is_dimension"] = True
        out["is_measure"] = False
    return out


def _normalize_sql(sql: str) -> str:
    """db.schema.table → schema.table یا table."""
    raw = (sql or "").strip().rstrip(";")
    raw = re.sub(
        r"\bFROM\s+[A-Za-z_][\w$]*\.(public|[A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)",
        r"FROM \1.\2",
        raw,
        flags=re.I,
    )
    raw = re.sub(
        r"\bJOIN\s+[A-Za-z_][\w$]*\.(public|[A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)",
        r"JOIN \1.\2",
        raw,
        flags=re.I,
    )
    return raw


def search_catalog(query: str, limit: int = 15) -> dict:
    """جستجو در کاتالوگ روی نام جدول، توضیح، تگ، ستون، business_name، synonyms."""
    q = (query or "").strip().lower()
    if not q:
        return {"tables": [], "message": "query خالی است"}
    tables = store.fetchall(
        """SELECT t.id, t.table_name, t.description, t.owner, t.tags, t.status,
                  t.row_count, t.last_update, s.schema_name, d.name AS db_name
           FROM tables t
           JOIN schemas s ON s.id=t.schema_id
           JOIN databases d ON d.id=s.database_id
           ORDER BY t.table_name"""
    )
    hits = []
    tokens = [t for t in re.findall(r"[\w\u0600-\u06FF]+", q) if len(t) > 1]
    for t in tables:
        score = 0
        blob = " ".join([
            str(t.get("table_name") or ""),
            str(t.get("description") or ""),
            str(t.get("tags") or ""),
            str(t.get("db_name") or ""),
            str(t.get("schema_name") or ""),
        ]).lower()
        if q in blob:
            score += 6
        for part in tokens:
            if part in blob:
                score += 2
        cols = store.fetchall(
            """SELECT column_name, business_name, description, synonyms, semantic_type,
                      is_measure, is_dimension, unit
               FROM columns WHERE table_id=?""",
            (t["id"],),
        )
        matched_cols = []
        for c in cols:
            cblob = " ".join([
                str(c.get("column_name") or ""),
                str(c.get("business_name") or ""),
                str(c.get("description") or ""),
                str(c.get("synonyms") or ""),
                str(c.get("semantic_type") or ""),
                str(c.get("unit") or ""),
            ]).lower()
            col_hit = q in cblob or any(p in cblob for p in tokens)
            if col_hit:
                score += 4
                matched_cols.append({
                    "column": c.get("column_name"),
                    "business_name": c.get("business_name"),
                    "semantic_type": c.get("semantic_type"),
                    "is_measure": bool(c.get("is_measure")),
                    "is_dimension": bool(c.get("is_dimension")),
                    "unit": c.get("unit"),
                })
        if score > 0:
            hits.append({
                "table_id": t["id"],
                "fqn": f"{t['db_name']}.{t['schema_name']}.{t['table_name']}",
                "table": t["table_name"],
                "database": t["db_name"],
                "schema": t["schema_name"],
                "description": (t.get("description") or "")[:240],
                "status": t.get("status"),
                "rows": t.get("row_count"),
                "last_update": t.get("last_update"),
                "matched_columns": matched_cols[:12],
                "score": score,
            })
    hits.sort(key=lambda x: -x["score"])
    return {"query": query, "count": len(hits), "tables": hits[:limit]}


def get_table_metadata(table_id: Optional[int] = None, table_name: Optional[str] = None) -> dict:
    """متادیتای کامل یک جدول + غنی‌سازی اگر خالی باشد."""
    tid = table_id
    if not tid and table_name:
        rows = store.fetchall(
            "SELECT id, table_name FROM tables WHERE lower(table_name) LIKE ?",
            (f"%{str(table_name).lower()}%",),
        )
        if not rows:
            return {"error": f"جدولی شبیه «{table_name}» پیدا نشد", "hint": "search_catalog را امتحان کن"}
        if len(rows) > 1:
            exact = [r for r in rows if (r["table_name"] or "").lower() == str(table_name).lower()]
            if len(exact) == 1:
                tid = exact[0]["id"]
            else:
                return {
                    "error": "چند جدول مشابه",
                    "candidates": [{"table_id": r["id"], "table": r["table_name"]} for r in rows[:12]],
                }
        else:
            tid = rows[0]["id"]
    if not tid:
        return {"error": "table_id یا table_name لازم است"}

    doc = services.ai_table_metadata(int(tid))
    if not doc:
        return {"error": "جدول یافت نشد"}

    enriched = []
    for c in doc.get("columns") or []:
        cc = dict(c)
        if not cc.get("semantic_type") and not cc.get("business_name"):
            guess = _infer_from_name(cc.get("name") or "", cc.get("type") or "")
            cc["business_name"] = cc.get("business_name") or guess["business_name"]
            cc["semantic_type"] = guess["semantic_type"] or None
            cc["unit"] = cc.get("unit") or guess["unit"] or None
            cc["is_measure"] = bool(cc.get("is_measure") or guess["is_measure"])
            cc["is_dimension"] = bool(cc.get("is_dimension") or guess["is_dimension"])
            cc["metadata_source"] = "inferred_from_name"
        else:
            cc["is_measure"] = bool(cc.get("is_measure"))
            cc["is_dimension"] = bool(cc.get("is_dimension"))
            cc["metadata_source"] = "stored"
        if isinstance(cc.get("synonyms"), str):
            cc["synonyms"] = _split_list(cc["synonyms"])
        enriched.append(cc)

    doc["columns"] = enriched
    doc["measures"] = [c["name"] for c in enriched if c.get("is_measure")]
    doc["dimensions"] = [c["name"] for c in enriched if c.get("is_dimension")]
    doc["temporal_columns"] = [
        c["name"] for c in enriched
        if (c.get("semantic_type") or "").lower() in ("temporal", "time", "date", "datetime", "year", "period")
        or any(x in (c.get("name") or "").lower() for x in ("year", "date", "time", "period", "month"))
    ]
    return doc


def list_tables_brief(limit: int = 80) -> dict:
    rows = store.fetchall(
        """SELECT t.id, t.table_name, t.status, t.row_count, t.last_update, t.description,
                  s.schema_name, d.name AS db_name,
                  (SELECT COUNT(*) FROM columns c WHERE c.table_id=t.id) AS ncols,
                  (SELECT COUNT(*) FROM columns c WHERE c.table_id=t.id
                     AND c.semantic_type IS NOT NULL AND c.semantic_type != '') AS rich_cols
           FROM tables t
           JOIN schemas s ON s.id=t.schema_id
           JOIN databases d ON d.id=s.database_id
           ORDER BY d.name, t.table_name
           LIMIT ?""",
        (int(limit),),
    )
    return {
        "count": len(rows),
        "tables": [
            {
                "table_id": r["id"],
                "fqn": f"{r['db_name']}.{r['schema_name']}.{r['table_name']}",
                "table": r["table_name"],
                "db": r["db_name"],
                "schema": r["schema_name"],
                "rows": r["row_count"],
                "status": r["status"],
                "last_update": r["last_update"],
                "description": (r.get("description") or "")[:160],
                "columns": r["ncols"],
                "has_rich_metadata": (r["rich_cols"] or 0) > 0,
            }
            for r in rows
        ],
    }


def get_freshness_info(table_name: Optional[str] = None, status_filter: Optional[str] = None) -> dict:
    dash = services.freshness_dashboard()
    tables = dash.get("tables") or []
    if table_name:
        q = table_name.lower()
        tables = [t for t in tables if q in (t.get("table") or "").lower() or q in (t.get("database") or "").lower()]
    if status_filter:
        sf = status_filter.lower()
        tables = [t for t in tables if (t.get("status") or "").lower() == sf]
    return {
        "source": "freshness",
        "kpis": dash.get("kpis"),
        "last_scan": dash.get("last_scan"),
        "tables": [
            {
                "table": t.get("table"),
                "database": t.get("database"),
                "last_update": t.get("last_update"),
                "delay_hours": t.get("delay_hours"),
                "expected_h": t.get("expected_interval_hours"),
                "sla_h": t.get("sla_hours"),
                "status": t.get("status"),
            }
            for t in tables[:50]
        ],
        "trend": (dash.get("trend") or [])[-14:],
    }


def get_quality_info(table_name: Optional[str] = None, check_type: Optional[str] = None) -> dict:
    by = services.quality_by_type()
    types = by.get("types") or []
    detail = by.get("by_type") or {}
    if check_type:
        ct = check_type.lower()
        detail = {k: v for k, v in detail.items() if ct in k.lower()}
        types = [t for t in types if ct in (t.get("check_type") or "").lower()]
    if table_name:
        q = table_name.lower()
        filtered = {}
        for k, bucket in detail.items():
            nb = dict(bucket)
            for key in ("fail", "warn", "pass", "all"):
                nb[key] = [
                    r for r in (bucket.get(key) or [])
                    if q in str(r.get("table_name") or "").lower()
                    or q in str(r.get("db_name") or "").lower()
                ]
            filtered[k] = nb
        detail = filtered
    compact = {}
    for k, bucket in detail.items():
        compact[k] = {
            "fail_count": len(bucket.get("fail") or []),
            "warn_count": len(bucket.get("warn") or []),
            "pass_count": len(bucket.get("pass") or []),
            "recent_fails": [
                {
                    "table": r.get("table_name"),
                    "db": r.get("db_name"),
                    "metric": r.get("metric"),
                    "value": r.get("value"),
                    "message": r.get("message"),
                }
                for r in (bucket.get("fail") or [])[:8]
            ],
        }
    health = services.health_board()[:15]
    return {
        "source": "quality",
        "summary_by_type": types,
        "details": compact,
        "lowest_health_tables": [
            {
                "table": h.get("table_name"),
                "db": h.get("db_name"),
                "overall": h.get("overall"),
                "status": h.get("status"),
            }
            for h in health
        ],
    }


def run_meta_sql(sql: str, limit: int = 100) -> dict:
    return services.sql_explore(sql, limit=limit, engine="meta")


def get_live_connection() -> Optional[dict]:
    try:
        store.init_schema()
    except Exception:
        pass
    try:
        store.execute(
            """CREATE TABLE IF NOT EXISTS db_connections (
                database_id INTEGER PRIMARY KEY,
                user_name TEXT,
                password TEXT
            )"""
        )
    except Exception:
        pass
    try:
        return store.fetchone(
            """SELECT d.id, d.name, d.host, d.port, d.db_type, c.user_name, c.password
               FROM databases d
               JOIN db_connections c ON c.database_id = d.id
               ORDER BY d.id DESC LIMIT 1"""
        )
    except Exception:
        return None


def run_live_sql(sql: str, limit: int = 300) -> dict:
    """SELECT فقط‌خواندنی روی Postgres زنده."""
    raw = _normalize_sql(sql)
    if not raw:
        return {"error": "SQL خالی است"}
    low = raw.lower()
    forbidden = [
        "insert", "update", "delete", "drop", "alter", "truncate", "create",
        "grant", "revoke", "copy", "call", "execute", "merge", "vacuum",
    ]
    tokens = set(re.findall(r"[a-z_]+", low))
    for f in forbidden:
        if f in tokens:
            return {"error": f"عملیات غیرمجاز: {f}", "sql": raw}
    if not (low.startswith("select") or low.startswith("with")):
        return {"error": "فقط SELECT مجاز است", "sql": raw}

    conn_info = get_live_connection()
    if not conn_info:
        return {
            "error": "اتصال زنده ثبت نشده. از تب Auto Discovery وصل شو.",
            "sql": raw,
        }
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        return {"error": "psycopg2 نصب نیست"}

    limit = max(1, min(int(limit or 300), 2000))
    try:
        conn = psycopg2.connect(
            host=conn_info["host"],
            port=int(conn_info["port"] or 5432),
            dbname=conn_info["name"],
            user=conn_info["user_name"] or "postgres",
            password=conn_info["password"] or "",
            connect_timeout=15,
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)
        q = raw
        if " limit " not in low:
            q = f"SELECT * FROM ({raw}) AS _q LIMIT {limit}"
        cur.execute(q)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        data = []
        for r in rows:
            row = dict(r)
            for k, v in list(row.items()):
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
                elif type(v).__name__ == "Decimal":
                    row[k] = float(v)
                elif isinstance(v, (bytes, memoryview)):
                    row[k] = str(v)
            data.append(row)
        cur.close()
        conn.close()
        return {
            "ok": True,
            "engine": "postgresql",
            "database": conn_info["name"],
            "host": conn_info["host"],
            "sql": raw,
            "columns": cols,
            "row_count": len(data),
            "rows": data[:limit],
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "sql": raw,
            "host": conn_info.get("host"),
            "database": conn_info.get("name"),
        }


def analyze_numbers(operation: str, values: List[float], labels: Optional[List[str]] = None) -> dict:
    try:
        nums = [float(v) for v in (values or []) if v is not None]
    except Exception as e:
        return {"error": f"اعداد نامعتبر: {e}"}
    if not nums:
        return {"error": "لیست اعداد خالی است"}
    op = (operation or "summary").lower().strip()
    result: Dict[str, Any] = {"operation": op, "n": len(nums)}
    if op in ("sum", "total"):
        result["value"] = sum(nums)
    elif op in ("avg", "mean", "average"):
        result["value"] = sum(nums) / len(nums)
    elif op == "min":
        result["value"] = min(nums)
        if labels and len(labels) == len(nums):
            result["label"] = labels[nums.index(result["value"])]
    elif op == "max":
        result["value"] = max(nums)
        if labels and len(labels) == len(nums):
            result["label"] = labels[nums.index(result["value"])]
    elif op == "median":
        s = sorted(nums)
        m = len(s) // 2
        result["value"] = s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2
    elif op in ("std", "stdev"):
        mean = sum(nums) / len(nums)
        result["value"] = math.sqrt(sum((x - mean) ** 2 for x in nums) / len(nums))
    elif op == "summary":
        s = sorted(nums)
        mean = sum(nums) / len(nums)
        result.update({"sum": sum(nums), "mean": mean, "min": s[0], "max": s[-1], "median": s[len(s) // 2]})
    else:
        return {"error": f"عملیات ناشناخته: {operation}"}
    return result


def build_chart(
    chart_type: str,
    labels: List[str],
    values: List[float],
    title: str = "",
    series_name: str = "value",
) -> dict:
    ct = (chart_type or "bar").lower()
    labs = [str(x) for x in (labels or [])]
    try:
        vals = [float(v) for v in (values or [])]
    except Exception:
        return {"error": "values باید عدد باشند"}
    n = min(len(labs), len(vals))
    labs, vals = labs[:n], vals[:n]
    if not vals:
        return {"error": "داده خالی"}
    if ct == "pie":
        data = [{
            "type": "pie", "labels": labs, "values": vals, "hole": 0.45,
            "textinfo": "label+percent",
            "marker": {"colors": ["#8b5cf6", "#06b6d4", "#22c55e", "#f59e0b", "#ef4444", "#3b82f6", "#ec4899"]},
        }]
    elif ct == "line":
        data = [{
            "type": "scatter", "mode": "lines+markers", "x": labs, "y": vals,
            "name": series_name, "line": {"color": "#8b5cf6", "width": 3},
            "marker": {"size": 7, "color": "#06b6d4"},
            "fill": "tozeroy", "fillcolor": "rgba(139,92,246,.12)",
        }]
    else:
        data = [{
            "type": "bar", "x": labs, "y": vals, "name": series_name,
            "marker": {"color": "#8b5cf6"},
        }]
    layout = {
        "title": {"text": title or series_name, "font": {"color": "#94a3b8", "size": 14}},
        "paper_bgcolor": "transparent", "plot_bgcolor": "transparent",
        "font": {"color": "#94a3b8"},
        "margin": {"t": 48, "b": 48, "l": 56, "r": 20},
        "xaxis": {"gridcolor": "rgba(148,163,184,.08)"},
        "yaxis": {"gridcolor": "rgba(148,163,184,.08)"},
    }
    return {"ok": True, "chart": {"data": data, "layout": layout}, "title": title, "n_points": len(vals)}


def run_python(code: str, data: Optional[list] = None) -> dict:
    """پایتون محدود برای محاسبه — نتیجه در متغیر result."""
    import statistics
    src = code or ""
    low = src.lower()
    blocked = [
        "open(", "exec(", "eval(", "compile(", "__import__", "subprocess",
        "socket", "pathlib", "shutil", "breakpoint", "input(", "os.system",
        "os.popen", "sys.exit",
    ]
    for b in blocked:
        if b in src or b in low:
            return {"error": f"کد غیرمجاز: {b}"}
    if re.search(r"^\s*import\s+", src, re.M) or re.search(r"^\s*from\s+\w+\s+import", src, re.M):
        return {"error": "import مجاز نیست — math و statistics از قبل موجودند"}

    safe_builtins = {
        "abs": abs, "min": min, "max": max, "sum": sum, "len": len, "range": range,
        "enumerate": enumerate, "zip": zip, "sorted": sorted, "round": round,
        "float": float, "int": int, "str": str, "bool": bool, "list": list,
        "dict": dict, "tuple": tuple, "set": set, "print": lambda *a, **k: None,
    }
    env = {
        "__builtins__": safe_builtins,
        "math": math,
        "statistics": statistics,
        "json": json,
        "rows": data or [],
        "result": None,
    }
    try:
        exec(src, env, env)  # noqa: S102
        out = env.get("result")

        def ser(x):
            if isinstance(x, dict):
                return {str(k): ser(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [ser(v) for v in x]
            if isinstance(x, (int, float, str, bool)) or x is None:
                return x
            if hasattr(x, "item"):
                try:
                    return x.item()
                except Exception:
                    pass
            return str(x)

        return {"ok": True, "result": ser(out)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


TOOL_IMPL = {
    "list_tables": list_tables_brief,
    "search_catalog": search_catalog,
    "get_table_metadata": get_table_metadata,
    "get_freshness_info": get_freshness_info,
    "get_quality_info": get_quality_info,
    "run_meta_sql": run_meta_sql,
    "run_live_sql": run_live_sql,
    "run_python": run_python,
    "analyze_numbers": analyze_numbers,
    "build_chart": build_chart,
    "get_live_connection": get_live_connection,
}

OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "List catalog tables (id, name, db, row counts, metadata flag).",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "Search tables/columns by business keywords using names, descriptions, synonyms, semantic types. Use this first for any data question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_metadata",
            "description": "Full column metadata for one table: business_name, description, synonyms, semantic_type, unit, is_measure, is_dimension, temporal_columns. Understand schema before writing SQL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_id": {"type": "integer"},
                    "table_name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_connection",
            "description": "Show live Postgres host/database if Discovery was done.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_live_sql",
            "description": "Run read-only SELECT on live Postgres. Use plain table names from metadata (e.g. income_statements), not database.schema.table. Always LIMIT results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_meta_sql",
            "description": "SELECT on Observatory internal SQLite meta (tables, columns, snapshots, quality, health).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_freshness_info",
            "description": "Data freshness / SLA status of tables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string"},
                    "status_filter": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_quality_info",
            "description": "Data quality checks and health scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string"},
                    "check_type": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_numbers",
            "description": "Math on a list of numbers: sum, avg, min, max, median, std, summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "values": {"type": "array", "items": {"type": "number"}},
                    "labels": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["operation", "values"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_chart",
            "description": "Build bar/line/pie chart from real labels and values for the UI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "values": {"type": "array", "items": {"type": "number"}},
                    "title": {"type": "string"},
                    "series_name": {"type": "string"},
                },
                "required": ["chart_type", "labels", "values"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Run restricted Python for custom calculations. Put final value in variable result. math, statistics, json, rows available.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
    },
]


def execute_tool(name: str, arguments: Dict[str, Any]) -> Any:
    fn = TOOL_IMPL.get(name)
    if not fn:
        return {"error": f"unknown tool: {name}"}
    args = arguments or {}
    try:
        import inspect
        sig = inspect.signature(fn)
        kwargs = {p: args[p] for p in sig.parameters if p in args}
        return fn(**kwargs)
    except TypeError as e:
        return {"error": f"bad args for {name}: {e}"}
    except Exception as e:
        return {"error": f"{name} failed: {e}"}
