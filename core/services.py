"""
Business logic for Data Observatory APIs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from . import store


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            continue
    return None


def _human_bytes(n: int) -> str:
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def _human_rows(n: int) -> str:
    n = int(n or 0)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} M"
    if n >= 1_000:
        return f"{n / 1_000:.1f} K"
    return str(n)


def _delay_hours(last_update: Optional[str]) -> float:
    dt = _parse_dt(last_update)
    if not dt:
        return 9999.0
    return max(0.0, (store.utc_now() - dt).total_seconds() / 3600)


def overview() -> dict[str, Any]:
    dbs = store.fetchall("SELECT * FROM databases")
    tables = store.fetchall("SELECT * FROM tables")
    alerts = store.fetchall("SELECT * FROM alerts WHERE status='OPEN'")
    last_scan = store.fetchone("SELECT * FROM scans ORDER BY id DESC LIMIT 1")
    scores = store.fetchall("SELECT overall FROM health_scores")

    total_rows = sum(int(t.get("row_count") or 0) for t in tables)
    total_size = sum(int(t.get("size_bytes") or 0) for t in tables)
    healthy = sum(1 for t in tables if t.get("status") == "healthy")
    warning = sum(1 for t in tables if t.get("status") == "warning")
    critical = sum(1 for t in tables if t.get("status") == "critical")
    stale = sum(1 for t in tables if t.get("status") in ("warning", "critical"))
    failed_checks = store.fetchall(
        "SELECT COUNT(*) AS c FROM quality_results WHERE status='FAIL'"
    )
    failed_n = failed_checks[0]["c"] if failed_checks else 0

    avg_health = round(sum(s["overall"] for s in scores) / len(scores), 1) if scores else 0
    freshness_pct = round(100 * healthy / max(1, len(tables)), 1)
    avg_growth = round(
        sum(float(t.get("growth_rate_pct") or 0) for t in tables) / max(1, len(tables)), 1
    )

    problematic = []
    for t in sorted(tables, key=lambda x: {"critical": 0, "warning": 1, "healthy": 2}.get(x["status"], 9)):
        if t["status"] == "healthy":
            continue
        sch = store.fetchone(
            """SELECT s.schema_name, d.name AS db_name FROM schemas s
               JOIN databases d ON d.id=s.database_id WHERE s.id=?""",
            (t["schema_id"],),
        )
        delay = _delay_hours(t.get("last_update"))
        issue = "No update" if delay > 48 else ("Delayed" if delay > 6 else "Quality issue")
        problematic.append(
            {
                "database": sch["db_name"] if sch else "?",
                "schema": sch["schema_name"] if sch else "?",
                "table": t["table_name"],
                "table_id": t["id"],
                "status": t["status"],
                "last_update": t.get("last_update"),
                "delay_hours": round(delay, 1),
                "rows": t["row_count"],
                "rows_human": _human_rows(t["row_count"]),
                "issue": issue,
            }
        )
        if len(problematic) >= 12:
            break

    return {
        "databases": len(dbs),
        "tables": len(tables),
        "records": total_rows,
        "records_human": _human_rows(total_rows),
        "size_bytes": total_size,
        "size_human": _human_bytes(total_size),
        "data_freshness_pct": freshness_pct,
        "health_score": avg_health,
        "stale_tables": stale,
        "failed_checks": failed_n,
        "growth_pct": avg_growth,
        "last_scan": last_scan,
        "status_breakdown": {"healthy": healthy, "warning": warning, "critical": critical},
        "problematic": problematic,
        "open_alerts": len(alerts),
        "db_list": [
            {
                "id": d["id"],
                "name": d["name"],
                "type": d["db_type"],
                "status": d["status"],
                "host": d["host"],
            }
            for d in dbs
        ],
    }


def catalog_tree() -> list[dict]:
    dbs = store.fetchall("SELECT * FROM databases ORDER BY name")
    tree = []
    for d in dbs:
        schemas = store.fetchall(
            "SELECT * FROM schemas WHERE database_id=? ORDER BY schema_name", (d["id"],)
        )
        s_nodes = []
        for s in schemas:
            tables = store.fetchall(
                "SELECT id, table_name, row_count, size_bytes, status, last_update FROM tables WHERE schema_id=? ORDER BY table_name",
                (s["id"],),
            )
            s_nodes.append(
                {
                    "id": s["id"],
                    "name": s["schema_name"],
                    "tables": [
                        {
                            "id": t["id"],
                            "name": t["table_name"],
                            "rows": t["row_count"],
                            "rows_human": _human_rows(t["row_count"]),
                            "size_human": _human_bytes(t["size_bytes"]),
                            "status": t["status"],
                            "last_update": t["last_update"],
                        }
                        for t in tables
                    ],
                }
            )
        tree.append(
            {
                "id": d["id"],
                "name": d["name"],
                "type": d["db_type"],
                "status": d["status"],
                "host": f"{d['host']}:{d['port']}",
                "schemas": s_nodes,
            }
        )
    return tree


def table_detail(table_id: int) -> Optional[dict]:
    t = store.fetchone("SELECT * FROM tables WHERE id=?", (table_id,))
    if not t:
        return None
    sch = store.fetchone(
        """SELECT s.schema_name, d.name AS db_name, d.db_type FROM schemas s
           JOIN databases d ON d.id=s.database_id WHERE s.id=?""",
        (t["schema_id"],),
    )
    cols = store.fetchall(
        "SELECT * FROM columns WHERE table_id=? ORDER BY ordinal_position", (table_id,)
    )
    hist = store.fetchall(
        "SELECT * FROM schema_history WHERE table_id=? ORDER BY change_time DESC LIMIT 20",
        (table_id,),
    )
    score = store.fetchone(
        "SELECT * FROM health_scores WHERE table_id=? ORDER BY id DESC LIMIT 1", (table_id,)
    )
    quality = store.fetchall(
        "SELECT * FROM quality_results WHERE table_id=? ORDER BY check_time DESC LIMIT 30",
        (table_id,),
    )
    delay = _delay_hours(t.get("last_update"))
    return {
        **t,
        "database": sch["db_name"] if sch else "?",
        "schema": sch["schema_name"] if sch else "?",
        "db_type": sch["db_type"] if sch else "?",
        "rows_human": _human_rows(t["row_count"]),
        "size_human": _human_bytes(t["size_bytes"]),
        "delay_hours": round(delay, 2),
        "columns": cols,
        "schema_history": hist,
        "health": score,
        "quality": quality,
    }


def freshness_list() -> list[dict]:
    rows = store.fetchall(
        """SELECT t.*, s.schema_name, d.name AS db_name
           FROM tables t
           JOIN schemas s ON s.id=t.schema_id
           JOIN databases d ON d.id=s.database_id
           ORDER BY t.last_update ASC"""
    )
    out = []
    for t in rows:
        delay = _delay_hours(t.get("last_update"))
        sla = float(t.get("sla_hours") or 24)
        expected = float(t.get("expected_interval_hours") or 24)
        if delay <= expected:
            st = "healthy"
        elif delay <= sla:
            st = "warning"
        else:
            st = "critical"
        out.append(
            {
                "table_id": t["id"],
                "database": t["db_name"],
                "schema": t["schema_name"],
                "table": t["table_name"],
                "expected_interval_hours": expected,
                "sla_hours": sla,
                "last_update": t["last_update"],
                "delay_hours": round(delay, 2),
                "status": st,
                "rows": t["row_count"],
                "rows_human": _human_rows(t["row_count"]),
            }
        )
    return out


def schema_changes(limit: int = 50) -> list[dict]:
    rows = store.fetchall(
        """SELECT h.*, t.table_name, s.schema_name, d.name AS db_name
           FROM schema_history h
           JOIN tables t ON t.id=h.table_id
           JOIN schemas s ON s.id=t.schema_id
           JOIN databases d ON d.id=s.database_id
           ORDER BY h.change_time DESC LIMIT ?""",
        (limit,),
    )
    return rows


def quality_summary() -> dict[str, Any]:
    results = store.fetchall(
        """SELECT q.*, t.table_name, d.name AS db_name
           FROM quality_results q
           JOIN tables t ON t.id=q.table_id
           JOIN schemas s ON s.id=t.schema_id
           JOIN databases d ON d.id=s.database_id
           ORDER BY q.check_time DESC LIMIT 200"""
    )
    by_status = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for r in results:
        by_status[r.get("status", "PASS")] = by_status.get(r.get("status", "PASS"), 0) + 1
    fails = [r for r in results if r.get("status") == "FAIL"]
    return {"by_status": by_status, "recent": results[:40], "failures": fails[:20]}


def profiler(table_id: int) -> Optional[dict]:
    detail = table_detail(table_id)
    if not detail:
        return None
    cols = detail["columns"]
    # synthetic histogram for consumption-like columns
    hist = []
    for i in range(12):
        hist.append({"bucket": f"{i * 5}-{(i + 1) * 5}", "count": int(8000 * (1 - abs(i - 4) / 8) ** 2 + 200)})
    return {
        "table": detail,
        "summary": {
            "rows": detail["row_count"],
            "columns": len(cols),
            "null_records_pct": round(
                sum(float(c.get("null_pct") or 0) for c in cols) / max(1, len(cols)), 2
            ),
            "duplicate_records_pct": 0.03 if detail["table_name"] == "MeterData" else 0.01,
        },
        "column_profiles": [
            {
                "name": c["column_name"],
                "type": c["data_type"],
                "null_pct": c["null_pct"],
                "distinct_pct": c["distinct_pct"],
                "example": c["example_value"],
                "min": c.get("min_val"),
                "max": c.get("max_val"),
                "mean": c.get("mean_val"),
            }
            for c in cols
        ],
        "histogram": hist,
    }


def growth_series(table_id: Optional[int] = None) -> dict[str, Any]:
    if table_id:
        snaps = store.fetchall(
            "SELECT * FROM table_snapshots WHERE table_id=? ORDER BY scan_time",
            (table_id,),
        )
        t = store.fetchone("SELECT table_name, growth_rate_pct, size_bytes, row_count FROM tables WHERE id=?", (table_id,))
        # simple forecast days to 100GB
        size = int(t["size_bytes"] or 1)
        growth = float(t["growth_rate_pct"] or 0.1) / 100
        days_to_100g = None
        if growth > 0 and size < 100_000_000_000:
            # weekly growth rate approx
            daily = growth / 7
            target = 100_000_000_000
            if daily > 0:
                import math
                days_to_100g = int(math.log(target / size) / math.log(1 + daily)) if size > 0 else None
        return {
            "table_id": table_id,
            "table_name": t["table_name"] if t else "?",
            "series": [
                {"date": s["scan_time"][:10], "rows": s["row_count"], "size_bytes": s["size_bytes"]}
                for s in snaps
            ],
            "growth_rate_pct": t["growth_rate_pct"] if t else 0,
            "forecast_days_to_100gb": days_to_100g,
        }
    # top tables by size
    tables = store.fetchall("SELECT id, table_name, row_count, size_bytes, growth_rate_pct FROM tables ORDER BY size_bytes DESC")
    return {
        "top_by_size": [
            {
                "table_id": t["id"],
                "table": t["table_name"],
                "rows": t["row_count"],
                "rows_human": _human_rows(t["row_count"]),
                "size_human": _human_bytes(t["size_bytes"]),
                "growth_rate_pct": t["growth_rate_pct"],
            }
            for t in tables
        ]
    }


def alerts_list() -> list[dict]:
    return store.fetchall(
        """SELECT a.*, t.table_name, d.name AS db_name
           FROM alerts a
           LEFT JOIN tables t ON t.id=a.table_id
           LEFT JOIN schemas s ON s.id=t.schema_id
           LEFT JOIN databases d ON d.id=s.database_id
           ORDER BY
             CASE a.severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END,
             a.created_at DESC"""
    )


def health_board() -> list[dict]:
    rows = store.fetchall(
        """SELECT h.*, t.table_name, t.status, d.name AS db_name
           FROM health_scores h
           JOIN tables t ON t.id=h.table_id
           JOIN schemas s ON s.id=t.schema_id
           JOIN databases d ON d.id=s.database_id
           ORDER BY h.overall ASC"""
    )
    return rows


def run_scan() -> dict:
    """Daily-style metadata & freshness scan for all tables.
    Updates last_scan, recomputes status from SLA, records snapshots + health scores.
    """
    now = store.utc_now()
    tables = store.fetchall("SELECT * FROM tables")
    dbs = store.fetchall("SELECT id FROM databases")
    store.execute(
        "INSERT INTO scans (started_at, finished_at, databases_scanned, tables_scanned, status) VALUES (?,?,?,?,?)",
        (store.iso(now), store.iso(now), len(dbs), len(tables), "success"),
    )
    critical = warning = healthy = 0
    for t in tables:
        tid = t["id"]
        delay = _delay_hours(t.get("last_update"))
        expected = float(t.get("expected_interval_hours") or 24)
        sla = float(t.get("sla_hours") or 26)
        if delay <= expected:
            st = "healthy"
            healthy += 1
        elif delay <= sla:
            st = "warning"
            warning += 1
        else:
            st = "critical"
            critical += 1
        store.execute(
            "UPDATE tables SET last_scan=?, status=? WHERE id=?",
            (store.iso(now), st, tid),
        )
        # snapshot for trend charts
        store.execute(
            """INSERT INTO table_snapshots
               (table_id, scan_time, row_count, size_bytes, last_record_time)
               VALUES (?,?,?,?,?)""",
            (tid, store.iso(now), t.get("row_count") or 0, t.get("size_bytes") or 0, t.get("last_update")),
        )
        # freshness-oriented health score
        freshness_s = max(0.0, 100.0 - delay * (8 if expected <= 2 else 2))
        overall = round(max(0.0, min(100.0, freshness_s * 0.6 + 40)), 1)
        store.execute(
            """INSERT INTO health_scores
               (table_id, scan_time, overall, freshness, completeness, duplicates, schema_score, validity, volume)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (tid, store.iso(now), overall, freshness_s, 95.0, 95.0, 100.0, 95.0, 90.0),
        )
    return {
        "ok": True,
        "databases": len(dbs),
        "tables": len(tables),
        "finished_at": store.iso(now),
        "status_breakdown": {"healthy": healthy, "warning": warning, "critical": critical},
    }



def spark_query_demo(payload: dict) -> dict:
    """Mock Spark analytics result."""
    group = payload.get("group_by", "companyCode")
    metric = payload.get("metric", "AVG(consumption)")
    table = payload.get("table", "MeterData")
    rows = [
        {"key": "504", "value": 18.21},
        {"key": "505", "value": 15.82},
        {"key": "506", "value": 23.91},
        {"key": "507", "value": 11.23},
        {"key": "508", "value": 19.05},
        {"key": "509", "value": 14.67},
        {"key": "510", "value": 21.40},
    ]
    return {
        "engine": "Apache Spark (simulated)",
        "table": table,
        "group_by": group,
        "metric": metric,
        "rows": rows,
        "execution_ms": 842,
    }


def sql_templates() -> list[dict]:
    return [
        {
            "id": "agg_company",
            "name": "Avg consumption by company",
            "category": "Aggregation",
            "sql": """SELECT
  companyCode,
  COUNT(*) AS records,
  AVG(consumption) AS avg_consumption,
  SUM(consumption) AS total_consumption
FROM MeterData
WHERE time >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY companyCode
ORDER BY avg_consumption DESC
LIMIT 100;""",
        },
        {
            "id": "fresh_check",
            "name": "Latest records per table",
            "category": "Freshness",
            "sql": """SELECT
  table_name,
  MAX(last_update) AS last_update,
  COUNT(*) AS snapshot_rows
FROM table_snapshots
GROUP BY table_name
ORDER BY last_update DESC
LIMIT 50;""",
        },
        {
            "id": "top_feeders",
            "name": "Top feeders by load",
            "category": "Ranking",
            "sql": """SELECT
  feeder_id,
  region,
  COUNT(*) AS events,
  AVG(voltage) AS avg_voltage
FROM MWS_FeederInfo
WHERE time >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY feeder_id, region
ORDER BY events DESC
LIMIT 25;""",
        },
        {
            "id": "null_audit",
            "name": "Null rate audit",
            "category": "Quality",
            "sql": """SELECT
  column_name,
  data_type,
  null_pct,
  distinct_pct
FROM columns
WHERE null_pct > 1
ORDER BY null_pct DESC
LIMIT 50;""",
        },
        {
            "id": "daily_growth",
            "name": "Daily row growth",
            "category": "Growth",
            "sql": """SELECT
  DATE(scan_time) AS day,
  SUM(row_count) AS total_rows,
  SUM(size_bytes) AS total_bytes
FROM table_snapshots
GROUP BY DATE(scan_time)
ORDER BY day DESC
LIMIT 30;""",
        },
        {
            "id": "join_demo",
            "name": "Meter × Customer sample",
            "category": "Join",
            "sql": """SELECT
  m.meterId,
  m.consumption,
  c.region,
  c.status
FROM MeterData m
LEFT JOIN Customer c ON c.meterId = m.meterId
WHERE m.time >= CURRENT_DATE - INTERVAL '1 day'
LIMIT 200;""",
        },
    ]



def _pg_connect():
    """Connect using last discovered credentials."""
    try:
        from .ai_tools import get_live_connection
        info = get_live_connection()
    except Exception:
        info = None
    if not info or not info.get("host"):
        return None, "اتصال زنده Postgres ثبت نشده. اول Auto Discovery بزن."
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        return None, "psycopg2 نصب نیست"
    try:
        conn = psycopg2.connect(
            host=info["host"],
            port=int(info["port"] or 5432),
            dbname=info["name"],
            user=info["user_name"] or "postgres",
            password=info["password"] or "",
            connect_timeout=12,
        )
        return conn, None
    except Exception as e:
        return None, str(e)


def sql_explore(sql: str, limit: int = 200, engine: str = "postgres") -> dict:
    """Read-only SQL explorer — primarily live PostgreSQL."""
    import re
    import time as _time

    raw = (sql or "").strip()
    if not raw:
        return {"ok": False, "error": "کوئری خالی است"}

    sql_l = raw.lower()
    no_comments = re.sub(r"--.*?$", "", sql_l, flags=re.M)
    no_comments = re.sub(r"/\*.*?\*/", "", no_comments, flags=re.S)

    forbidden = [
        "insert", "update", "delete", "drop", "alter", "truncate",
        "create", "grant", "revoke", "merge", "replace", "attach",
        "detach", "vacuum", "reindex", "copy", "call", "execute",
    ]
    tokens = set(re.findall(r"[a-z_]+", no_comments))
    for f in forbidden:
        if f in tokens:
            try:
                store.execute(
                    "INSERT INTO query_history (sql_text, engine, row_count, duration_ms, status, error, created_at) VALUES (?,?,?,?,?,?,?)",
                    (raw[:4000], engine, 0, 0, "BLOCKED", f"Write blocked: {f}", store.iso(store.utc_now())),
                )
            except Exception:
                pass
            return {"ok": False, "error": f"عملیات نوشتن مسدود شد: {f}", "blocked": True}

    stmts = [s.strip() for s in raw.split(";") if s.strip()]
    if len(stmts) > 1:
        return {"ok": False, "error": "فقط یک statement در هر بار مجاز است."}

    limit = max(1, min(int(limit or 200), 5000))
    t0 = _time.time()
    engine = (engine or "postgres").lower()

    # Meta SQLite path when querying observatory tables or engine=meta
    local_tables = {
        "databases", "schemas", "tables", "columns", "table_snapshots",
        "schema_history", "quality_results", "alerts", "scans", "health_scores",
        "query_history", "ml_experiments",
    }
    used_local = any(re.search(rf"\b{t}\b", no_comments) for t in local_tables)
    force_meta = engine in ("meta", "sqlite", "observatory")

    columns: list = []
    data: list = []
    source = "postgres"
    explain = []

    try:
        if force_meta or (used_local and engine != "postgres"):
            q = raw.rstrip(";")
            if not re.search(r"\blimit\b", no_comments):
                q = f"SELECT * FROM ({q}) AS _q LIMIT {limit}"
            with store.conn() as c:
                cur = c.execute(q)
                colnames = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchmany(limit)
                columns = colnames
                data = [dict(zip(colnames, r)) for r in rows]
            source = "observatory_meta"
            explain = [{"id": 1, "op": "SCAN", "detail": "Observatory SQLite meta"}, {"id": 2, "op": "LIMIT", "detail": f"max {limit}"}]
        else:
            conn, err = _pg_connect()
            if err:
                return {"ok": False, "error": err, "hint": "از تب Auto Discovery وصل شو"}
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            q = raw.rstrip(";")
            # EXPLAIN if requested via comment flag handled separately
            if not re.search(r"\blimit\b", no_comments) and (q.lower().startswith("select") or q.lower().startswith("with")):
                q = f"SELECT * FROM ({q}) AS _q LIMIT {limit}"
            cur.execute(q)
            rows = cur.fetchmany(limit)
            columns = [d[0] for d in cur.description] if cur.description else []
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
            # explain plan
            try:
                cur.execute("EXPLAIN " + raw.rstrip(";"))
                explain = [{"id": i + 1, "op": "PLAN", "detail": list(r.values())[0] if r else ""} for i, r in enumerate(cur.fetchall())]
            except Exception:
                explain = []
            cur.close()
            conn.close()
            source = "postgresql"

        duration_ms = int((_time.time() - t0) * 1000)
        try:
            store.execute(
                "INSERT INTO query_history (sql_text, engine, row_count, duration_ms, status, error, created_at) VALUES (?,?,?,?,?,?,?)",
                (raw[:4000], source, len(data), duration_ms, "OK", "", store.iso(store.utc_now())),
            )
        except Exception:
            pass
        return {
            "ok": True,
            "columns": columns,
            "rows": data,
            "row_count": len(data),
            "duration_ms": duration_ms,
            "engine": source,
            "explain": explain,
            "sql": raw,
        }
    except Exception as e:
        duration_ms = int((_time.time() - t0) * 1000)
        try:
            store.execute(
                "INSERT INTO query_history (sql_text, engine, row_count, duration_ms, status, error, created_at) VALUES (?,?,?,?,?,?,?)",
                (raw[:4000], engine, 0, duration_ms, "ERROR", str(e)[:500], store.iso(store.utc_now())),
            )
        except Exception:
            pass
        return {"ok": False, "error": str(e), "duration_ms": duration_ms, "engine": engine}


def sql_list_live_tables() -> dict:
    """List tables from live Postgres with size estimates."""
    conn, err = _pg_connect()
    if err:
        # fallback catalog
        rows = store.fetchall(
            """SELECT t.table_name, t.row_count, t.size_bytes, s.schema_name, d.name AS db_name, t.id
               FROM tables t JOIN schemas s ON s.id=t.schema_id JOIN databases d ON d.id=s.database_id
               ORDER BY t.table_name"""
        )
        return {
            "ok": True, "source": "catalog",
            "tables": [
                {"name": r["table_name"], "schema": r["schema_name"], "db": r["db_name"],
                 "rows": r["row_count"], "size_bytes": r["size_bytes"], "table_id": r["id"]}
                for r in rows
            ],
        }
    try:
        from psycopg2.extras import RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT n.nspname AS schema,
                   c.relname AS name,
                   c.reltuples::bigint AS rows_est,
                   pg_total_relation_size(c.oid) AS size_bytes,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS size_pretty
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r'
              AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            ORDER BY n.nspname, c.relname
            """
        )
        tables = []
        for r in cur.fetchall():
            tables.append({
                "schema": r["schema"],
                "name": r["name"],
                "rows": int(r["rows_est"] or 0),
                "size_bytes": int(r["size_bytes"] or 0),
                "size_pretty": r["size_pretty"],
            })
        cur.close()
        conn.close()
        return {"ok": True, "source": "postgresql", "tables": tables}
    except Exception as e:
        return {"ok": False, "error": str(e), "tables": []}


def sql_table_data(table_name: str, schema: str = "public", offset: int = 0, limit: int = 100) -> dict:
    """Browse table rows (DataGrip-style)."""
    import re
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table_name or ""):
        return {"ok": False, "error": "نام جدول نامعتبر"}
    if schema and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", schema):
        return {"ok": False, "error": "schema نامعتبر"}
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    conn, err = _pg_connect()
    if err:
        return {"ok": False, "error": err}
    try:
        from psycopg2.extras import RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        fq = f'"{schema}"."{table_name}"'
        cur.execute(f"SELECT COUNT(*) AS c FROM {fq}")
        total = int(cur.fetchone()["c"])
        cur.execute(f"SELECT * FROM {fq} OFFSET %s LIMIT %s", (offset, limit))
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
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
            "table": table_name,
            "schema": schema,
            "columns": columns,
            "rows": data,
            "total": total,
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def sql_table_info(table_name: str, schema: str = "public") -> dict:
    """Columns, PK, FK, indexes, size for a table."""
    import re
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table_name or ""):
        return {"ok": False, "error": "نام جدول نامعتبر"}
    if schema and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", schema):
        schema = "public"
    conn, err = _pg_connect()
    if err:
        return {"ok": False, "error": err}
    try:
        from psycopg2.extras import RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # columns
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default, character_maximum_length, numeric_precision
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            ORDER BY ordinal_position
            """,
            (schema, table_name),
        )
        columns = [dict(r) for r in cur.fetchall()]
        # primary keys
        cur.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema=%s AND tc.table_name=%s
            ORDER BY kcu.ordinal_position
            """,
            (schema, table_name),
        )
        pk = [r["column_name"] for r in cur.fetchall()]
        # foreign keys
        cur.execute(
            """
            SELECT
              kcu.column_name,
              ccu.table_schema AS foreign_table_schema,
              ccu.table_name AS foreign_table_name,
              ccu.column_name AS foreign_column_name,
              tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema=%s AND tc.table_name=%s
            """,
            (schema, table_name),
        )
        fks = [dict(r) for r in cur.fetchall()]
        # indexes
        cur.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname=%s AND tablename=%s
            ORDER BY indexname
            """,
            (schema, table_name),
        )
        indexes = [dict(r) for r in cur.fetchall()]
        # size + row estimate
        cur.execute(
            """
            SELECT
              pg_total_relation_size(quote_ident(%s)||'.'||quote_ident(%s)) AS total_bytes,
              pg_relation_size(quote_ident(%s)||'.'||quote_ident(%s)) AS table_bytes,
              pg_indexes_size(quote_ident(%s)||'.'||quote_ident(%s)) AS index_bytes,
              pg_size_pretty(pg_total_relation_size(quote_ident(%s)||'.'||quote_ident(%s))) AS total_pretty,
              (SELECT reltuples::bigint FROM pg_class c
               JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname=%s AND c.relname=%s) AS rows_est
            """,
            (schema, table_name, schema, table_name, schema, table_name, schema, table_name, schema, table_name),
        )
        size = dict(cur.fetchone() or {})
        cur.close()
        conn.close()
        return {
            "ok": True,
            "table": table_name,
            "schema": schema,
            "columns": columns,
            "primary_key": pk,
            "foreign_keys": fks,
            "indexes": indexes,
            "size": size,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}



def sql_history(limit: int = 30) -> list[dict]:
    return store.fetchall(
        "SELECT * FROM query_history ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def bi_settings() -> dict:
    import os
    return {
        "superset_url": os.environ.get("SUPERSET_URL", "http://localhost:8088"),
        "embed_path": "/superset/welcome/",
        "hint": "docker compose -f docker-compose.superset.yml up -d",
        "default_user": "admin",
        "default_password": "admin",
    }


def bi_query(body: dict) -> dict:
    """Aggregate query for BI studio — safe identifiers only."""
    import re
    from .ai_tools import run_live_sql, get_live_connection

    def ident(name: str) -> str:
        n = (name or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n):
            raise ValueError(f"invalid identifier: {name}")
        return n

    table = ident(body.get("table") or "")
    schema = body.get("schema") or "public"
    if schema and schema != "public":
        schema = ident(schema)
        fq = f"{schema}.{table}"
    else:
        fq = table

    dimensions = [ident(d) for d in (body.get("dimensions") or []) if d]
    legend = body.get("legend")
    if legend:
        legend = ident(legend)
        if legend not in dimensions:
            dimensions.append(legend)

    measures_in = body.get("measures") or []
    if not measures_in:
        return {"ok": False, "error": "حداقل یک measure لازم است"}

    allowed_agg = {
        "sum": "SUM", "avg": "AVG", "mean": "AVG", "count": "COUNT",
        "min": "MIN", "max": "MAX", "count_distinct": "COUNT",
    }
    measure_sql = []
    measure_meta = []
    for i, m in enumerate(measures_in):
        if isinstance(m, str):
            col, agg = m, "sum"
        else:
            col = m.get("column") or m.get("field")
            agg = (m.get("agg") or "sum").lower()
        col = ident(col)
        if agg not in allowed_agg:
            agg = "sum"
        alias = ident(m.get("alias") if isinstance(m, dict) and m.get("alias") else f"m{i}_{agg}_{col}"[:50])
        if agg == "count_distinct":
            expr = f"COUNT(DISTINCT {col}) AS {alias}"
        elif agg == "count":
            expr = f"COUNT({col}) AS {alias}"
        else:
            expr = f"{allowed_agg[agg]}({col}) AS {alias}"
        measure_sql.append(expr)
        measure_meta.append({"column": col, "agg": agg, "alias": alias})

    select_parts = list(dimensions) + measure_sql
    group = f" GROUP BY {', '.join(dimensions)}" if dimensions else ""
    order = f" ORDER BY {dimensions[0]}" if dimensions else ""
    limit = max(1, min(int(body.get("limit") or 5000), 20000))
    sql = f"SELECT {', '.join(select_parts)} FROM {fq}{group}{order} LIMIT {limit}"

    if not get_live_connection():
        return {"ok": False, "error": "اتصال زنده ثبت نشده — اول Auto Discovery", "sql": sql}

    res = run_live_sql(sql, limit=limit)
    if not isinstance(res, dict):
        return {"ok": False, "error": "query failed", "sql": sql}
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or "query failed", "sql": sql}
    return {
        "ok": True,
        "sql": sql,
        "columns": res.get("columns") or [],
        "rows": res.get("rows") or [],
        "row_count": res.get("row_count") or 0,
        "dimensions": dimensions,
        "measures": measure_meta,
        "legend": legend,
    }



def discover_postgres(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    schema_filter: str | None = None,
) -> dict:
    """Connect to real PostgreSQL and register schemas/tables/columns into observatory store."""
    if not (host or "").strip():
        return {"ok": False, "error": "Host را وارد کنید — اتصال پیش‌فرضی تنظیم نشده است."}
    if not (database or "").strip():
        return {"ok": False, "error": "نام دیتابیس لازم است."}
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        return {"ok": False, "error": "psycopg2 not installed. pip install psycopg2-binary"}

    try:
        conn = psycopg2.connect(
            host=host, port=int(port), dbname=database, user=user, password=password,
            connect_timeout=10,
        )
    except Exception as e:
        return {"ok": False, "error": f"Connection failed: {e}"}

    schemas_n = tables_n = cols_n = 0
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # register database
        existing = store.fetchone(
            "SELECT id FROM databases WHERE name=? AND host=? AND port=?",
            (database, host, int(port)),
        )
        if existing:
            db_id = existing["id"]
            store.execute("UPDATE databases SET status='online' WHERE id=?", (db_id,))
            # clear previous catalog for this db
            old_schemas = store.fetchall("SELECT id FROM schemas WHERE database_id=?", (db_id,))
            for s in old_schemas:
                tids = store.fetchall("SELECT id FROM tables WHERE schema_id=?", (s["id"],))
                for t in tids:
                    store.execute("DELETE FROM columns WHERE table_id=?", (t["id"],))
                    store.execute("DELETE FROM table_snapshots WHERE table_id=?", (t["id"],))
                    store.execute("DELETE FROM quality_results WHERE table_id=?", (t["id"],))
                    store.execute("DELETE FROM schema_history WHERE table_id=?", (t["id"],))
                    store.execute("DELETE FROM health_scores WHERE table_id=?", (t["id"],))
                    store.execute("DELETE FROM alerts WHERE table_id=?", (t["id"],))
                store.execute("DELETE FROM tables WHERE schema_id=?", (s["id"],))
            store.execute("DELETE FROM schemas WHERE database_id=?", (db_id,))
        else:
            store.execute(
                "INSERT INTO databases (name, db_type, host, port, status, created_at) VALUES (?,?,?,?,?,?)",
                (database, "PostgreSQL", host, int(port), "online", store.iso(store.utc_now())),
            )
            db_id = store.fetchone("SELECT id FROM databases WHERE name=? AND host=? ORDER BY id DESC", (database, host))["id"]

        # save credentials lightly in tags on db? use a connections table if needed - skip password storage in plain for now
        # store connection string in a simple key table
        try:
            store.execute(
                """CREATE TABLE IF NOT EXISTS db_connections (
                    database_id INTEGER PRIMARY KEY,
                    user_name TEXT,
                    password TEXT,
                    FOREIGN KEY (database_id) REFERENCES databases(id) ON DELETE CASCADE
                )"""
            )
            store.execute("DELETE FROM db_connections WHERE database_id=?", (db_id,))
            store.execute(
                "INSERT INTO db_connections (database_id, user_name, password) VALUES (?,?,?)",
                (db_id, user, password),
            )
        except Exception:
            pass

        cur.execute(
            """
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
              AND schema_name NOT LIKE 'pg_temp%'
              AND schema_name NOT LIKE 'pg_toast_temp%'
            ORDER BY schema_name
            """
        )
        schema_rows = cur.fetchall()
        if schema_filter:
            schema_rows = [r for r in schema_rows if r["schema_name"] == schema_filter]

        for sr in schema_rows:
            sname = sr["schema_name"]
            store.execute(
                "INSERT INTO schemas (database_id, schema_name) VALUES (?,?)",
                (db_id, sname),
            )
            sid = store.fetchone(
                "SELECT id FROM schemas WHERE database_id=? AND schema_name=? ORDER BY id DESC",
                (db_id, sname),
            )["id"]
            schemas_n += 1

            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema=%s AND table_type='BASE TABLE'
                ORDER BY table_name
                """,
                (sname,),
            )
            for tr in cur.fetchall():
                tname = tr["table_name"]
                # row count + size (best effort)
                row_count = 0
                size_bytes = 0
                last_update = None
                try:
                    cur.execute(
                        "SELECT reltuples::bigint AS est FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname=%s AND c.relname=%s",
                        (sname, tname),
                    )
                    est = cur.fetchone()
                    if est and est.get("est") is not None:
                        row_count = max(0, int(est["est"]))
                except Exception:
                    pass
                try:
                    cur.execute(
                        "SELECT pg_total_relation_size(%s::regclass) AS sz",
                        (f'"{sname}"."{tname}"',),
                    )
                    sz = cur.fetchone()
                    if sz and sz.get("sz") is not None:
                        size_bytes = int(sz["sz"])
                except Exception:
                    pass
                # try max time-like column for freshness
                try:
                    cur.execute(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema=%s AND table_name=%s
                          AND (data_type LIKE 'timestamp%%' OR column_name ILIKE '%%time%%'
                               OR column_name ILIKE '%%date%%' OR column_name='updated_at')
                        ORDER BY ordinal_position LIMIT 1
                        """,
                        (sname, tname),
                    )
                    tc = cur.fetchone()
                    if tc:
                        ccol = tc["column_name"]
                        cur.execute(
                            f'SELECT MAX("{ccol}") AS m FROM "{sname}"."{tname}"'
                        )
                        mx = cur.fetchone()
                        if mx and mx.get("m") is not None:
                            last_update = str(mx["m"])[:19]
                except Exception:
                    conn.rollback()
                    cur = conn.cursor(cursor_factory=RealDictCursor)

                status = "healthy"
                store.execute(
                    """INSERT INTO tables
                       (schema_id, table_name, row_count, size_bytes, last_update, last_scan, status,
                        expected_interval_hours, sla_hours, description, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        sid, tname, row_count, size_bytes, last_update,
                        store.iso(store.utc_now()), status, 24, 26, "", store.iso(store.utc_now()),
                    ),
                )
                tid = store.fetchone(
                    "SELECT id FROM tables WHERE schema_id=? AND table_name=? ORDER BY id DESC",
                    (sid, tname),
                )["id"]
                tables_n += 1

                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable, ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema=%s AND table_name=%s
                    ORDER BY ordinal_position
                    """,
                    (sname, tname),
                )
                for i, col in enumerate(cur.fetchall()):
                    store.execute(
                        """INSERT INTO columns
                           (table_id, column_name, data_type, nullable, ordinal_position,
                            null_pct, distinct_pct, example_value, description)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (
                            tid, col["column_name"], col["data_type"],
                            1 if col["is_nullable"] == "YES" else 0,
                            col["ordinal_position"] or i,
                            0, 50, None, "",
                        ),
                    )
                    cols_n += 1
        cur.close()
        conn.close()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}

    # Apply any metadata packs from data/metadata/*.json (match by table_name)
    meta_result = None
    try:
        from .metadata_loader import apply_all_packs
        meta_result = apply_all_packs()
    except Exception as e:
        meta_result = {"ok": False, "error": str(e)}

    return {
        "ok": True,
        "connection": "successful",
        "host": host,
        "port": port,
        "database": database,
        "db_type": "PostgreSQL",
        "schemas": schemas_n,
        "tables": tables_n,
        "columns": cols_n,
        "metadata_applied": meta_result,
        "message": f"Registered {schemas_n} schemas, {tables_n} tables, {cols_n} columns",
    }


def discover_demo(host: str, port: int, database: str, db_type: str = "PostgreSQL", user: str = "", password: str = "") -> dict:
    if (db_type or "").lower().startswith("postgres") and user:
        return discover_postgres(host, port, database, user, password)
    return {
        "ok": False,
        "error": "برای اتصال واقعی PostgreSQL فیلدهای user و password لازم است.",
    }


def clear_demo_data() -> dict:
    store.clear_all_catalog()
    return {"ok": True, "message": "تمام داده‌های کاتالوگ پاک شد"}



def update_table_sla(table_id: int, expected_hours: float, sla_hours: float) -> dict:
    store.execute(
        "UPDATE tables SET expected_interval_hours=?, sla_hours=? WHERE id=?",
        (float(expected_hours), float(sla_hours), int(table_id)),
    )
    # recompute status based on delay
    t = store.fetchone("SELECT * FROM tables WHERE id=?", (table_id,))
    if not t:
        return {"ok": False, "error": "table not found"}
    from datetime import datetime
    last = t.get("last_update")
    delay_h = 0.0
    if last:
        try:
            lu = datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")
            delay_h = max(0.0, (datetime.utcnow() - lu).total_seconds() / 3600.0)
        except Exception:
            pass
    status = "healthy"
    if delay_h > float(sla_hours):
        status = "critical"
    elif delay_h > float(expected_hours):
        status = "warning"
    store.execute("UPDATE tables SET status=? WHERE id=?", (status, table_id))
    # alert if needed
    if status in ("warning", "critical"):
        sev = "CRITICAL" if status == "critical" else "WARNING"
        store.execute(
            "INSERT INTO alerts (table_id, severity, message, created_at) VALUES (?,?,?,?)",
            (
                table_id,
                sev,
                f"Table {t['table_name']} freshness delay {delay_h:.1f}h (expected every {expected_hours}h, SLA {sla_hours}h)",
                store.iso(store.utc_now()),
            ),
        )
    return {"ok": True, "status": status, "delay_hours": round(delay_h, 2)}


def update_table_metadata(table_id: int, description: str = "", owner: str = "", tags: str = "") -> dict:
    store.execute(
        "UPDATE tables SET description=?, owner=?, tags=? WHERE id=?",
        (description or "", owner or "", tags or "", int(table_id)),
    )
    return {"ok": True}


def _split_list(val: Optional[str]) -> list[str]:
    if not val:
        return []
    s = str(val).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            import json
            arr = json.loads(s)
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
    return [x.strip() for x in s.replace(";", ",").split(",") if x.strip()]


def update_column_metadata(column_id: int, **kwargs) -> dict:
    """Update rich AI-oriented column metadata. Accepts any of the rich fields."""
    allowed = {
        "description", "is_pii", "is_pk",
        "business_name", "semantic_type", "unit", "synonyms",
        "business_definition", "calculation_formula", "allowed_values",
        "example_value", "is_measure", "is_dimension", "ai_notes",
    }
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if k in ("is_pii", "is_pk", "is_measure", "is_dimension"):
            sets.append(f"{k}=?")
            vals.append(1 if v in (True, 1, "1", "true", "True") else 0)
        elif k in ("synonyms", "allowed_values") and isinstance(v, list):
            sets.append(f"{k}=?")
            vals.append(", ".join(str(x) for x in v))
        else:
            sets.append(f"{k}=?")
            vals.append("" if v is None else str(v))
    if not sets:
        return {"ok": False, "error": "no valid fields"}
    vals.append(int(column_id))
    store.execute(f"UPDATE columns SET {', '.join(sets)} WHERE id=?", tuple(vals))
    return {"ok": True}


def _infer_semantic(cname: str, dtype: str) -> dict:
    """Heuristic enrichment for auto-metadata."""
    low = (cname or "").lower()
    dt = (dtype or "").lower()
    out = {
        "business_name": cname.replace("_", " ").title() if cname else "",
        "semantic_type": "",
        "unit": "",
        "is_measure": 0,
        "is_dimension": 0,
        "is_pk": 0,
        "is_pii": 0,
        "synonyms": "",
    }
    if low in ("id", "pk") or low.endswith("_id") or low.endswith("id") and "time" not in low and "date" not in low:
        if low in ("id", "meterid", "device_id", "customer_id", "user_id"):
            out["is_pk"] = 1
        out["semantic_type"] = "identifier"
        out["is_dimension"] = 1
    if any(x in low for x in ("time", "date", "timestamp", "created", "updated", "timetag")):
        out["semantic_type"] = "temporal"
        out["is_dimension"] = 1
    if any(x in low for x in ("phone", "email", "national", "ssn", "mobile", "firstname", "lastname", "fullname")):
        out["is_pii"] = 1
        out["semantic_type"] = out["semantic_type"] or "pii"
    if any(x in low for x in ("amount", "price", "cost", "revenue", "consumption", "kwh", "qty", "quantity", "count", "total", "avg", "sum", "value", "score", "rate", "pct", "percent")):
        out["is_measure"] = 1
        out["semantic_type"] = out["semantic_type"] or "measure"
        if "kwh" in low or "consumption" in low:
            out["unit"] = "kWh"
        elif any(x in low for x in ("amount", "price", "cost", "revenue")):
            out["unit"] = "currency"
        elif any(x in low for x in ("pct", "percent", "rate")):
            out["unit"] = "percent"
    if any(x in low for x in ("status", "type", "category", "code", "region", "zone", "class")):
        out["semantic_type"] = out["semantic_type"] or "categorical"
        out["is_dimension"] = 1
    if "int" in dt or "numeric" in dt or "double" in dt or "float" in dt or "decimal" in dt or "real" in dt:
        if not out["semantic_type"]:
            out["semantic_type"] = "numeric"
            out["is_measure"] = 1
    if "char" in dt or "text" in dt or "varchar" in dt:
        if not out["semantic_type"]:
            out["semantic_type"] = "text"
            out["is_dimension"] = 1
    # simple synonyms from name
    parts = [p for p in low.replace("-", "_").split("_") if p]
    if len(parts) > 1:
        out["synonyms"] = ", ".join(parts)
    return out


def auto_generate_metadata(table_id: int) -> dict:
    """Generate rich AI-oriented metadata for table + columns if empty."""
    detail = table_detail(table_id)
    if not detail:
        return {"ok": False, "error": "not found"}
    tname = detail["table_name"]
    if not (detail.get("description") or "").strip():
        desc = (
            f"Business table `{tname}` in {detail.get('database')}.{detail.get('schema')}. "
            f"Approx rows={detail.get('row_count')}, last_update={detail.get('last_update') or 'n/a'}, "
            f"status={detail.get('status')}."
        )
        store.execute("UPDATE tables SET description=? WHERE id=?", (desc, table_id))
    updated = 0
    for c in detail.get("columns") or []:
        # skip if already has rich description
        if (c.get("description") or "").strip() and (c.get("semantic_type") or "").strip():
            continue
        cname = c["column_name"]
        dtype = c.get("data_type") or "unknown"
        inferred = _infer_semantic(cname, dtype)
        bits = [f"Column `{cname}` ({dtype})."]
        if c.get("nullable"):
            bits.append(f"Nullable; null≈{c.get('null_pct') or 0}%.")
        else:
            bits.append("NOT NULL.")
        if c.get("example_value"):
            bits.append(f"Example: {c['example_value']}.")
        desc = (c.get("description") or "").strip() or " ".join(bits)
        store.execute(
            """UPDATE columns SET
                description=?, is_pii=?, is_pk=?,
                business_name=COALESCE(NULLIF(business_name,''), ?),
                semantic_type=COALESCE(NULLIF(semantic_type,''), ?),
                unit=COALESCE(NULLIF(unit,''), ?),
                synonyms=COALESCE(NULLIF(synonyms,''), ?),
                is_measure=CASE WHEN is_measure=1 THEN 1 ELSE ? END,
                is_dimension=CASE WHEN is_dimension=1 THEN 1 ELSE ? END
               WHERE id=?""",
            (
                desc,
                inferred["is_pii"] or int(c.get("is_pii") or 0),
                inferred["is_pk"] or int(c.get("is_pk") or 0),
                inferred["business_name"],
                inferred["semantic_type"],
                inferred["unit"],
                inferred["synonyms"],
                inferred["is_measure"],
                inferred["is_dimension"],
                c["id"],
            ),
        )
        updated += 1
    return {"ok": True, "columns_updated": updated, "table": table_detail(table_id)}


def quality_by_type() -> dict:
    """Group quality results by check_type with failures separated."""
    results = store.fetchall(
        """SELECT q.*, t.table_name, d.name AS db_name
           FROM quality_results q
           JOIN tables t ON t.id=q.table_id
           JOIN schemas s ON s.id=t.schema_id
           JOIN databases d ON d.id=s.database_id
           ORDER BY q.check_time DESC LIMIT 500"""
    )
    types = {}
    for r in results:
        ct = r.get("check_type") or "other"
        types.setdefault(ct, {"all": [], "fail": [], "warn": [], "pass": []})
        types[ct]["all"].append(r)
        st = (r.get("status") or "PASS").upper()
        if st == "FAIL":
            types[ct]["fail"].append(r)
        elif st == "WARN":
            types[ct]["warn"].append(r)
        else:
            types[ct]["pass"].append(r)
    summary = []
    for ct, bucket in sorted(types.items()):
        summary.append({
            "check_type": ct,
            "total": len(bucket["all"]),
            "fail": len(bucket["fail"]),
            "warn": len(bucket["warn"]),
            "pass": len(bucket["pass"]),
        })
    return {"types": summary, "by_type": types}


def freshness_dashboard() -> dict[str, Any]:
    """Rich freshness view: KPIs, per-table status, and trend series from health_scores / snapshots."""
    rows = freshness_list()
    healthy = sum(1 for r in rows if r["status"] == "healthy")
    warning = sum(1 for r in rows if r["status"] == "warning")
    critical = sum(1 for r in rows if r["status"] == "critical")
    total = len(rows) or 1
    avg_delay = round(sum(r["delay_hours"] for r in rows) / total, 2) if rows else 0
    on_sla = sum(1 for r in rows if r["status"] != "critical")
    # trend: daily avg freshness score from health_scores (last 30 days)
    hist = store.fetchall(
        """SELECT date(scan_time) AS day,
                  AVG(freshness) AS avg_freshness,
                  AVG(overall) AS avg_overall,
                  COUNT(*) AS n
           FROM health_scores
           WHERE scan_time >= datetime('now', '-30 days')
           GROUP BY date(scan_time)
           ORDER BY day"""
    )
    # per-table recent freshness series (for selected charts)
    table_trends = {}
    for r in rows[:40]:
        tid = r["table_id"]
        series = store.fetchall(
            """SELECT date(scan_time) AS day, freshness, overall
               FROM health_scores WHERE table_id=?
               ORDER BY scan_time DESC LIMIT 14""",
            (tid,),
        )
        table_trends[tid] = list(reversed(series)) if series else []
    last_scan = store.fetchone(
        "SELECT * FROM scans ORDER BY id DESC LIMIT 1"
    )
    return {
        "kpis": {
            "total_tables": len(rows),
            "healthy": healthy,
            "warning": warning,
            "critical": critical,
            "on_sla_pct": round(100.0 * on_sla / total, 1),
            "avg_delay_hours": avg_delay,
        },
        "tables": rows,
        "trend": hist,
        "table_trends": table_trends,
        "last_scan": last_scan,
    }


def ai_table_metadata(table_id: int) -> Optional[dict]:
    """Produce a precise, AI/agent-optimized metadata document for a single table.
    Designed for RAG, agents, and LLM tool-calling (stable schema, no fluff).
    """
    detail = table_detail(table_id)
    if not detail:
        return None
    cols = []
    for c in detail.get("columns") or []:
        syn = _split_list(c.get("synonyms"))
        allowed = _split_list(c.get("allowed_values"))
        cols.append({
            "name": c.get("column_name"),
            "business_name": (c.get("business_name") or "").strip() or None,
            "type": c.get("data_type"),
            "nullable": bool(c.get("nullable")),
            "ordinal": c.get("ordinal_position"),
            "description": (c.get("description") or "").strip() or None,
            "business_definition": (c.get("business_definition") or "").strip() or None,
            "semantic_type": (c.get("semantic_type") or "").strip() or None,
            "unit": (c.get("unit") or "").strip() or None,
            "synonyms": syn or None,
            "calculation_formula": (c.get("calculation_formula") or "").strip() or None,
            "allowed_values": allowed or None,
            "example_value": c.get("example_value"),
            "is_primary_key": bool(c.get("is_pk")),
            "is_pii": bool(c.get("is_pii")),
            "is_measure": bool(c.get("is_measure")),
            "is_dimension": bool(c.get("is_dimension")),
            "ai_notes": (c.get("ai_notes") or "").strip() or None,
            "stats": {
                "null_pct": c.get("null_pct"),
                "distinct_pct": c.get("distinct_pct"),
                "min": c.get("min_val"),
                "max": c.get("max_val"),
                "mean": c.get("mean_val"),
            },
        })
    fq_name = f"{detail.get('database')}.{detail.get('schema')}.{detail.get('table_name')}"
    tags = [t.strip() for t in (detail.get("tags") or "").split(",") if t.strip()]
    measures = [c["name"] for c in cols if c.get("is_measure")]
    dimensions = [c["name"] for c in cols if c.get("is_dimension")]
    doc = {
        "entity_type": "table",
        "format": "data_observatory.column_metadata.v2",
        "fully_qualified_name": fq_name,
        "database": detail.get("database"),
        "schema": detail.get("schema"),
        "table": detail.get("table_name"),
        "db_type": detail.get("db_type"),
        "description": (detail.get("description") or "").strip() or None,
        "owner": (detail.get("owner") or "").strip() or None,
        "tags": tags,
        "row_count": detail.get("row_count"),
        "size_bytes": detail.get("size_bytes"),
        "last_update": detail.get("last_update"),
        "last_scan": detail.get("last_scan"),
        "status": detail.get("status"),
        "sla": {
            "expected_interval_hours": detail.get("expected_interval_hours"),
            "sla_hours": detail.get("sla_hours"),
            "delay_hours": detail.get("delay_hours"),
        },
        "columns": cols,
        "primary_keys": [c["name"] for c in cols if c["is_primary_key"]],
        "pii_columns": [c["name"] for c in cols if c["is_pii"]],
        "measures": measures,
        "dimensions": dimensions,
        "health": {
            "overall": (detail.get("health") or {}).get("overall"),
            "freshness": (detail.get("health") or {}).get("freshness"),
            "completeness": (detail.get("health") or {}).get("completeness"),
            "duplicates": (detail.get("health") or {}).get("duplicates"),
            "validity": (detail.get("health") or {}).get("validity"),
        } if detail.get("health") else None,
        "schema_history": [
            {"time": h.get("change_time"), "type": h.get("change_type"), "detail": h.get("detail")}
            for h in (detail.get("schema_history") or [])[:10]
        ],
        "agent_hints": {
            "prefer_filter_columns": [
                c["name"] for c in cols
                if c.get("is_dimension") or (c["name"] and any(
                    x in (c["name"] or "").lower() for x in ("time", "date", "id", "code", "status")
                ))
            ][:10],
            "safe_for_join": [c["name"] for c in cols if c["is_primary_key"] or (c["name"] or "").lower().endswith("id")],
            "measures_for_aggregate": measures[:12],
            "dimensions_for_group_by": dimensions[:12],
            "avoid_select_star": True,
            "pii_handling": "mask or exclude" if any(c["is_pii"] for c in cols) else "none_detected",
        },
    }
    return doc


def ai_catalog_export(limit: int = 500) -> dict:
    """Export catalog in AI-ready form for bulk ingestion by agents."""
    tables = store.fetchall(
        """SELECT t.id FROM tables t
           JOIN schemas s ON s.id=t.schema_id
           JOIN databases d ON d.id=s.database_id
           ORDER BY d.name, s.schema_name, t.table_name
           LIMIT ?""",
        (int(limit),),
    )
    items = []
    for t in tables:
        doc = ai_table_metadata(t["id"])
        if doc:
            items.append(doc)
    return {
        "format": "data_observatory.ai_catalog.v1",
        "generated_at": store.iso(store.utc_now()),
        "count": len(items),
        "tables": items,
    }



def bi_export_pdf(payload: dict) -> dict:
    """Export dashboard as one PDF page matching on-screen layout (positions/sizes)."""
    import base64
    import io
    from datetime import datetime, timezone
    from pathlib import Path

    widgets = payload.get("widgets") or []
    title = (payload.get("title") or "Data Observatory — BI Dashboard").strip()
    canvas_meta = payload.get("canvas") or {}
    if not widgets:
        return {"ok": False, "error": "هیچ نموداری روی بوم نیست"}

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as pdfcanvas
        from reportlab.lib.utils import ImageReader
    except ImportError:
        return {"ok": False, "error": "reportlab نصب نیست: pip install reportlab"}

    out_dir = Path(__file__).resolve().parent.parent / "data" / "bi_exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"bi_dashboard_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
    fpath = out_dir / fname

    # canvas bounds from widgets
    cw = float(canvas_meta.get("width") or 0)
    ch = float(canvas_meta.get("height") or 0)
    if cw < 10 or ch < 10:
        max_r = max((float(w.get("x") or 0) + float(w.get("w") or 400) for w in widgets), default=1000)
        max_b = max((float(w.get("y") or 0) + float(w.get("h") or 300) for w in widgets), default=700)
        cw, ch = max(max_r + 40, 800), max(max_b + 40, 600)

    page = landscape(A4)
    W, H = page
    c = pdfcanvas.Canvas(str(fpath), pagesize=page)

    # background
    c.setFillColorRGB(0.04, 0.06, 0.11)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    # header bar
    c.setFillColorRGB(0.545, 0.361, 0.965)
    c.rect(0, H - 16 * mm, W, 16 * mm, fill=1, stroke=0)
    c.setFillColorRGB(0.02, 0.75, 0.85)
    c.rect(0, H - 17.2 * mm, W, 1.2 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(12 * mm, H - 10.5 * mm, title[:90])
    c.setFont("Helvetica", 8)
    c.drawRightString(W - 12 * mm, H - 10.5 * mm, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    # content area under header
    margin = 8 * mm
    area_x, area_y = margin, margin
    area_w, area_h = W - 2 * margin, H - 16 * mm - 2 * margin
    scale = min(area_w / cw, area_h / ch)

    for w in widgets:
        b64 = w.get("image") or w.get("png") or ""
        if "," in b64 and "base64" in b64[:40]:
            b64 = b64.split(",", 1)[1]
        if not b64:
            continue
        try:
            raw = base64.b64decode(b64)
            img = ImageReader(io.BytesIO(raw))
            wx = float(w.get("x") or 0) * scale + area_x
            # PDF y is bottom-up; convert from top-left canvas coords
            wy_top = float(w.get("y") or 0) * scale
            ww = float(w.get("w") or 400) * scale
            wh = float(w.get("h") or 300) * scale
            wy = area_y + area_h - wy_top - wh
            # card shadow-ish border
            c.setFillColorRGB(0.08, 0.11, 0.18)
            c.roundRect(wx - 1, wy - 1, ww + 2, wh + 2, 4, fill=1, stroke=0)
            c.drawImage(img, wx, wy, width=ww, height=wh, mask="auto", preserveAspectRatio=True, anchor="c")
        except Exception:
            continue

    c.save()
    return {"ok": True, "path": str(fpath), "filename": fname, "url": f"/api/bi/exports/{fname}"}




def _ws_dirs():
    from pathlib import Path
    base = Path(__file__).resolve().parent.parent / "data" / "workspace"
    d = base / "dashboards"
    n = base / "notebooks"
    d.mkdir(parents=True, exist_ok=True)
    n.mkdir(parents=True, exist_ok=True)
    return d, n


def _ws_index(folder, kind: str) -> dict:
    """index.json: {items: [{id, name, ...}]}"""
    import json
    p = folder / "index.json"
    if not p.exists():
        return {"next_id": 1, "items": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"next_id": 1, "items": []}


def _ws_write_index(folder, data: dict) -> None:
    import json
    p = folder / "index.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _workspace_ensure():
    _ws_dirs()
    try:
        from . import store
        store.ensure_workspace_tables()
    except Exception:
        pass


def bi_list_dashboards() -> dict:
    import json
    d, _ = _ws_dirs()
    idx = _ws_index(d, "dash")
    items = sorted(idx.get("items") or [], key=lambda x: -int(x.get("id") or 0))
    return {"ok": True, "items": items}


def bi_get_dashboard(dash_id: int) -> dict:
    import json
    d, _ = _ws_dirs()
    path = d / f"{int(dash_id)}.json"
    if not path.exists():
        return {"ok": False, "error": f"داشبورد #{dash_id} پیدا نشد"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "id": int(dash_id),
        "name": data.get("name") or f"Dashboard {dash_id}",
        "payload": data.get("payload") or {},
        "updated_at": data.get("updated_at"),
        "created_at": data.get("created_at"),
    }


def bi_save_dashboard(name: str, payload: dict, dash_id: int | None = None) -> dict:
    import json
    from datetime import datetime, timezone
    try:
        d, _ = _ws_dirs()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        name = (name or "Dashboard").strip() or "Dashboard"
        idx = _ws_index(d, "dash")
        if dash_id:
            did = int(dash_id)
            path = d / f"{did}.json"
            created = now
            if path.exists():
                try:
                    created = json.loads(path.read_text(encoding="utf-8")).get("created_at") or now
                except Exception:
                    pass
            data = {"id": did, "name": name, "payload": payload or {}, "updated_at": now, "created_at": created}
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            # update index
            items = [x for x in (idx.get("items") or []) if int(x.get("id") or 0) != did]
            items.append({"id": did, "name": name, "updated_at": now, "created_at": created})
            idx["items"] = items
            _ws_write_index(d, idx)
            return {"ok": True, "id": did, "name": name, "updated_at": now}
        # new
        did = int(idx.get("next_id") or 1)
        idx["next_id"] = did + 1
        data = {"id": did, "name": name, "payload": payload or {}, "updated_at": now, "created_at": now}
        (d / f"{did}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        items = idx.get("items") or []
        items.append({"id": did, "name": name, "updated_at": now, "created_at": now})
        idx["items"] = items
        _ws_write_index(d, idx)
        return {"ok": True, "id": did, "name": name, "updated_at": now}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def bi_delete_dashboard(dash_id: int) -> dict:
    d, _ = _ws_dirs()
    path = d / f"{int(dash_id)}.json"
    if path.exists():
        path.unlink()
    idx = _ws_index(d, "dash")
    idx["items"] = [x for x in (idx.get("items") or []) if int(x.get("id") or 0) != int(dash_id)]
    _ws_write_index(d, idx)
    return {"ok": True}


def nb_list_notebooks() -> dict:
    _, n = _ws_dirs()
    idx = _ws_index(n, "nb")
    items = sorted(idx.get("items") or [], key=lambda x: -int(x.get("id") or 0))
    return {"ok": True, "items": items}


def nb_get_notebook(nb_id: int) -> dict:
    import json
    _, n = _ws_dirs()
    path = n / f"{int(nb_id)}.json"
    if not path.exists():
        return {"ok": False, "error": f"نوت‌بوک #{nb_id} پیدا نشد"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "id": int(nb_id),
        "name": data.get("name") or f"Notebook {nb_id}",
        "table_name": data.get("table_name") or "",
        "cells": data.get("cells") or [],
        "updated_at": data.get("updated_at"),
        "created_at": data.get("created_at"),
    }


def nb_save_notebook(name: str, cells: list, table_name: str = "", nb_id: int | None = None) -> dict:
    import json
    from datetime import datetime, timezone
    try:
        _, n = _ws_dirs()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        name = (name or "Notebook").strip() or "Notebook"
        idx = _ws_index(n, "nb")
        if nb_id:
            nid = int(nb_id)
            path = n / f"{nid}.json"
            created = now
            if path.exists():
                try:
                    created = json.loads(path.read_text(encoding="utf-8")).get("created_at") or now
                except Exception:
                    pass
            data = {
                "id": nid, "name": name, "table_name": table_name or "",
                "cells": cells or [], "updated_at": now, "created_at": created,
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            items = [x for x in (idx.get("items") or []) if int(x.get("id") or 0) != nid]
            items.append({"id": nid, "name": name, "table_name": table_name or "", "updated_at": now, "created_at": created})
            idx["items"] = items
            _ws_write_index(n, idx)
            return {"ok": True, "id": nid, "name": name, "updated_at": now}
        nid = int(idx.get("next_id") or 1)
        idx["next_id"] = nid + 1
        data = {
            "id": nid, "name": name, "table_name": table_name or "",
            "cells": cells or [], "updated_at": now, "created_at": now,
        }
        (n / f"{nid}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        items = idx.get("items") or []
        items.append({"id": nid, "name": name, "table_name": table_name or "", "updated_at": now, "created_at": now})
        idx["items"] = items
        _ws_write_index(n, idx)
        return {"ok": True, "id": nid, "name": name, "updated_at": now}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def nb_delete_notebook(nb_id: int) -> dict:
    _, n = _ws_dirs()
    path = n / f"{int(nb_id)}.json"
    if path.exists():
        path.unlink()
    idx = _ws_index(n, "nb")
    idx["items"] = [x for x in (idx.get("items") or []) if int(x.get("id") or 0) != int(nb_id)]
    _ws_write_index(n, idx)
    return {"ok": True}


