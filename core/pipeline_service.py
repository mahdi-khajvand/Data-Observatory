
"""Data Pipeline / Warehouse studio — DAG builder, joins, schedule, load modes."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "workspace" / "pipelines"
DATA_ROOT.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _index() -> dict:
    p = DATA_ROOT / "index.json"
    if not p.exists():
        return {"next_id": 1, "items": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"next_id": 1, "items": []}


def _write_index(idx: dict) -> None:
    (DATA_ROOT / "index.json").write_text(
        json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _path(pid: int) -> Path:
    return DATA_ROOT / f"{int(pid)}.json"


def list_pipelines() -> dict:
    idx = _index()
    items = sorted(idx.get("items") or [], key=lambda x: -int(x.get("id") or 0))
    return {"ok": True, "items": items}


def get_pipeline(pid: int) -> dict:
    path = _path(pid)
    if not path.exists():
        return {"ok": False, "error": f"پایپ‌لاین #{pid} پیدا نشد"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "pipeline": data}


def save_pipeline(body: dict) -> dict:
    try:
        idx = _index()
        now = _now()
        name = (body.get("name") or "Pipeline").strip() or "Pipeline"
        pid = body.get("id")
        payload = {
            "name": name,
            "description": body.get("description") or "",
            "warehouse": body.get("warehouse") or {},
            "nodes": body.get("nodes") or [],
            "edges": body.get("edges") or [],
            "schedule": body.get("schedule") or {"enabled": False, "cron": "0 2 * * *", "timezone": "Asia/Tehran"},
            "load_mode": body.get("load_mode") or "full",
            "status": body.get("status") or "draft",
            "updated_at": now,
        }
        if pid:
            pid = int(pid)
            path = _path(pid)
            created = now
            if path.exists():
                try:
                    created = json.loads(path.read_text(encoding="utf-8")).get("created_at") or now
                except Exception:
                    pass
            payload["id"] = pid
            payload["created_at"] = created
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            items = [x for x in (idx.get("items") or []) if int(x.get("id") or 0) != pid]
            items.append(_summary(payload))
            idx["items"] = items
            _write_index(idx)
            return {"ok": True, "id": pid, "pipeline": payload}
        pid = int(idx.get("next_id") or 1)
        idx["next_id"] = pid + 1
        payload["id"] = pid
        payload["created_at"] = now
        _path(pid).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        items = idx.get("items") or []
        items.append(_summary(payload))
        idx["items"] = items
        _write_index(idx)
        return {"ok": True, "id": pid, "pipeline": payload}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _summary(p: dict) -> dict:
    wh = p.get("warehouse") or {}
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "status": p.get("status") or "draft",
        "load_mode": p.get("load_mode") or "full",
        "nodes": len(p.get("nodes") or []),
        "warehouse_db": wh.get("database") or "",
        "host": wh.get("host") or "",
        "schedule": (p.get("schedule") or {}).get("cron") or "",
        "updated_at": p.get("updated_at"),
        "created_at": p.get("created_at"),
    }


def delete_pipeline(pid: int) -> dict:
    path = _path(pid)
    if path.exists():
        path.unlink()
    idx = _index()
    idx["items"] = [x for x in (idx.get("items") or []) if int(x.get("id") or 0) != int(pid)]
    _write_index(idx)
    return {"ok": True}


def lake_tables() -> dict:
    """Tables available as sources — live Postgres first, then catalog store."""
    tables = []
    try:
        from .ai_tools import get_live_connection, run_live_sql
        if get_live_connection():
            res = run_live_sql(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                LIMIT 500
                """,
                limit=500,
            )
            if isinstance(res, dict) and res.get("ok"):
                for row in res.get("rows") or []:
                    tables.append({
                        "schema": row.get("table_schema") or "public",
                        "table": row.get("table_name"),
                        "source": "live",
                    })
    except Exception as e:
        return {"ok": True, "tables": tables, "warning": str(e)}

    if not tables:
        try:
            from . import store
            rows = store.fetchall(
                "SELECT t.id, t.name AS table_name, s.name AS schema_name "
                "FROM tables t LEFT JOIN schemas s ON s.id = t.schema_id LIMIT 300"
            )
            for r in rows:
                tables.append({
                    "schema": r.get("schema_name") or "public",
                    "table": r.get("table_name"),
                    "table_id": r.get("id"),
                    "source": "catalog",
                })
        except Exception:
            pass
    return {"ok": True, "tables": tables, "count": len(tables)}


def table_columns(schema: str, table: str) -> dict:
    schema = schema or "public"
    try:
        from .ai_tools import get_live_connection, run_live_sql
        if get_live_connection():
            # safe identifiers
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema or "public"):
                schema = "public"
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table or ""):
                return {"ok": False, "error": "invalid table name"}
            res = run_live_sql(
                f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = '{schema}' AND table_name = '{table}'
                ORDER BY ordinal_position
                """,
                limit=500,
            )
            if isinstance(res, dict) and res.get("ok"):
                cols = [
                    {
                        "name": r.get("column_name"),
                        "type": r.get("data_type"),
                        "nullable": str(r.get("is_nullable") or "").upper() == "YES",
                    }
                    for r in (res.get("rows") or [])
                ]
                return {"ok": True, "schema": schema, "table": table, "columns": cols}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "schema": schema, "table": table, "columns": []}


def create_warehouse(body: dict) -> dict:
    """Register (and optionally CREATE DATABASE) a target warehouse."""
    host = (body.get("host") or "").strip()
    port = int(body.get("port") or 5432)
    database = (body.get("database") or "").strip()
    user = (body.get("user") or "").strip()
    password = body.get("password") or ""
    schema = (body.get("schema") or "mart").strip() or "mart"
    name = (body.get("name") or database or "Warehouse").strip()

    if not host or not database:
        return {"ok": False, "error": "host و database الزامی است"}

    created_db = False
    created_schema = False
    note = ""
    try:
        import psycopg2
        # try connect to target db
        try:
            conn = psycopg2.connect(
                host=host, port=port, dbname=database, user=user, password=password, connect_timeout=8
            )
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                created_schema = True
            conn.close()
            note = "اتصال موفق؛ schema آماده است"
        except Exception as e1:
            # try create database via postgres db
            try:
                conn = psycopg2.connect(
                    host=host, port=port, dbname="postgres", user=user, password=password, connect_timeout=8
                )
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
                    if not cur.fetchone():
                        cur.execute(f'CREATE DATABASE "{database}"')
                        created_db = True
                conn.close()
                conn = psycopg2.connect(
                    host=host, port=port, dbname=database, user=user, password=password, connect_timeout=8
                )
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                    created_schema = True
                conn.close()
                note = "دیتابیس ساخته شد و schema آماده است" if created_db else "schema آماده است"
            except Exception as e2:
                note = f"ثبت منطقی — اتصال مستقیم ممکن نشد: {e2}"
    except ImportError:
        note = "psycopg2 نیست — فقط ثبت منطقی"

    warehouse = {
        "name": name,
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
        "schema": schema,
        "created_db": created_db,
        "created_schema": created_schema,
        "note": note,
    }
    # seed empty pipeline bound to this warehouse
    result = save_pipeline({
        "name": name,
        "description": body.get("description") or f"Warehouse {database}@{host}",
        "warehouse": warehouse,
        "nodes": [],
        "edges": [],
        "schedule": {"enabled": False, "cron": "0 2 * * *", "timezone": "Asia/Tehran"},
        "load_mode": body.get("load_mode") or "full",
        "status": "draft",
    })
    if not result.get("ok"):
        return result
    return {
        "ok": True,
        "warehouse": warehouse,
        "pipeline_id": result.get("id"),
        "pipeline": result.get("pipeline"),
        "note": note,
    }


def compile_sql(pipeline: dict) -> dict:
    """Generate approximate SQL from DAG (sources + joins + output)."""
    nodes = {n["id"]: n for n in (pipeline.get("nodes") or []) if n.get("id")}
    edges = pipeline.get("edges") or []
    children: dict[str, list] = {}
    parents: dict[str, list] = {}
    for e in edges:
        fr, to = e.get("from"), e.get("to")
        if not fr or not to:
            continue
        children.setdefault(fr, []).append(to)
        parents.setdefault(to, []).append(fr)

    join_nodes = [n for n in nodes.values() if n.get("type") == "join"]
    output_nodes = [n for n in nodes.values() if n.get("type") == "output"]
    source_nodes = [n for n in nodes.values() if n.get("type") == "source"]

    wh = pipeline.get("warehouse") or {}
    target_schema = wh.get("schema") or "mart"
    load_mode = pipeline.get("load_mode") or "full"

    lines = ["-- Auto-compiled from Pipeline Studio DAG", f"-- load_mode: {load_mode}", ""]

    if not source_nodes:
        return {"ok": True, "sql": "-- هنوز منبع (source) اضافه نشده", "steps": []}

    steps = []
    # simple path: if one join with two sources
    if join_nodes:
        j = join_nodes[0]
        pars = parents.get(j["id"]) or []
        left = nodes.get(pars[0]) if len(pars) > 0 else None
        right = nodes.get(pars[1]) if len(pars) > 1 else None
        on_list = j.get("on") or []
        jt = (j.get("join_type") or "inner").upper()
        if left and right:
            lname = left.get("table") or "left"
            rname = right.get("table") or "right"
            lschema = left.get("schema") or "public"
            rschema = right.get("schema") or "public"
            lcols = left.get("selected_columns") or left.get("columns") or ["*"]
            rcols = right.get("selected_columns") or right.get("columns") or ["*"]
            if lcols == ["*"] or not lcols:
                select_l = [f"l.*"]
            else:
                select_l = [f"l.{c}" for c in lcols]
            if rcols == ["*"] or not rcols:
                select_r = []
            else:
                select_r = [f"r.{c}" for c in rcols if c not in (lcols or [])]
            select_clause = ", ".join(select_l + select_r) or "l.*"
            on_sql = " AND ".join(
                f"l.{o.get('left_col')} = r.{o.get('right_col')}"
                for o in on_list if o.get("left_col") and o.get("right_col")
            ) or "TRUE"
            sql_join = (
                f"SELECT {select_clause}\n"
                f"FROM {lschema}.{lname} l\n"
                f"{jt} JOIN {rschema}.{rname} r ON {on_sql}"
            )
            steps.append({"step": "join", "sql": sql_join})
            lines.append(f"-- Step: JOIN {lname} ⋈ {rname}")
            lines.append(sql_join)
            lines.append("")
    else:
        for s in source_nodes:
            cols = s.get("selected_columns") or ["*"]
            col_sql = ", ".join(cols) if cols else "*"
            sch = s.get("schema") or "public"
            tbl = s.get("table")
            q = f"SELECT {col_sql} FROM {sch}.{tbl}"
            steps.append({"step": "source", "sql": q})
            lines.append(f"-- Source: {sch}.{tbl}")
            lines.append(q)
            lines.append("")

    for out in output_nodes:
        target = out.get("target_table") or "pipeline_output"
        keys = out.get("upsert_keys") or []
        mode = out.get("load_mode") or load_mode
        lines.append(f"-- Output → {target_schema}.{target} ({mode})")
        if mode == "upsert" and keys:
            lines.append(f"-- UPSERT keys: {', '.join(keys)}")
            lines.append(
                f"-- INSERT INTO {target_schema}.{target} … ON CONFLICT ({', '.join(keys)}) DO UPDATE SET …"
            )
        else:
            lines.append(f"-- FULL refresh: TRUNCATE {target_schema}.{target}; INSERT INTO … SELECT …")
        steps.append({"step": "output", "target": f"{target_schema}.{target}", "mode": mode})

    schedule = pipeline.get("schedule") or {}
    if schedule.get("enabled"):
        lines.append(f"-- Schedule: cron={schedule.get('cron')} tz={schedule.get('timezone')}")

    return {"ok": True, "sql": "\n".join(lines), "steps": steps}


def pipeline_info(pid: int) -> dict:
    r = get_pipeline(pid)
    if not r.get("ok"):
        return r
    p = r["pipeline"]
    compiled = compile_sql(p)
    nodes = p.get("nodes") or []
    return {
        "ok": True,
        "pipeline": p,
        "stats": {
            "sources": sum(1 for n in nodes if n.get("type") == "source"),
            "joins": sum(1 for n in nodes if n.get("type") == "join"),
            "transforms": sum(1 for n in nodes if n.get("type") == "transform"),
            "outputs": sum(1 for n in nodes if n.get("type") == "output"),
            "comments": sum(1 for n in nodes if n.get("type") == "comment"),
            "edges": len(p.get("edges") or []),
        },
        "sql": compiled.get("sql"),
        "steps": compiled.get("steps"),
    }



def _ident(name: str) -> str:
    n = (name or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n):
        raise ValueError(f"invalid identifier: {name}")
    return n


def _wh_connect(warehouse: dict):
    import psycopg2
    return psycopg2.connect(
        host=warehouse.get("host"),
        port=int(warehouse.get("port") or 5432),
        dbname=warehouse.get("database"),
        user=warehouse.get("user"),
        password=warehouse.get("password") or "",
        connect_timeout=12,
    )


def _build_select_for_node(pipeline: dict, node_id: str) -> dict:
    """Build a SELECT (or source scan) representing the data at node_id."""
    nodes = {n["id"]: n for n in (pipeline.get("nodes") or []) if n.get("id")}
    edges = pipeline.get("edges") or []
    parents = {}
    for e in edges:
        parents.setdefault(e.get("to"), []).append(e.get("from"))

    def build(nid: str) -> str:
        n = nodes.get(nid)
        if not n:
            raise ValueError(f"node {nid} missing")
        t = n.get("type")
        if t == "source":
            sch = _ident(n.get("schema") or "public")
            tbl = _ident(n.get("table") or "")
            cols = n.get("selected_columns") or []
            if cols and cols != ["*"]:
                col_sql = ", ".join(_ident(c) for c in cols)
            else:
                col_sql = "*"
            return f"SELECT {col_sql} FROM {sch}.{tbl}"
        if t == "join":
            pars = parents.get(nid) or []
            if len(pars) < 2:
                # one parent only — pass through
                if len(pars) == 1:
                    return build(pars[0])
                raise ValueError("Join needs two inputs")
            left_sql = build(pars[0])
            right_sql = build(pars[1])
            on_list = n.get("on") or []
            jt = (n.get("join_type") or "inner").upper()
            if jt not in ("INNER", "LEFT", "RIGHT", "FULL"):
                jt = "INNER"
            on_sql = " AND ".join(
                f"l.{_ident(o.get('left_col'))} = r.{_ident(o.get('right_col'))}"
                for o in on_list if o.get("left_col") and o.get("right_col")
            ) or "TRUE"
            return (
                f"SELECT l.*, r.* FROM ({left_sql}) l "
                f"{jt} JOIN ({right_sql}) r ON {on_sql}"
            )
        if t == "transform":
            pars = parents.get(nid) or []
            if not pars:
                raise ValueError("Transform needs input")
            base = build(pars[0])
            ops = n.get("ops") or []
            sql = f"SELECT * FROM ({base}) t"
            # lightweight: DISTINCT for dedupe
            if "dedupe" in ops:
                sql = f"SELECT DISTINCT * FROM ({base}) t"
            return sql
        if t == "output":
            pars = parents.get(nid) or []
            if not pars:
                raise ValueError("Output needs input")
            return build(pars[0])
        if t == "comment":
            raise ValueError("comment has no data")
        raise ValueError(f"unknown node type {t}")

    sql = build(node_id)
    return {"ok": True, "sql": sql}


def preview_node(pid: int, node_id: str, limit: int = 50) -> dict:
    """Preview data at a node — source from live lake or compiled subquery."""
    r = get_pipeline(pid)
    if not r.get("ok"):
        return r
    p = r["pipeline"]
    nodes = {n["id"]: n for n in (p.get("nodes") or [])}
    node = nodes.get(node_id)
    if not node:
        return {"ok": False, "error": "گره پیدا نشد"}
    if node.get("type") == "comment":
        return {"ok": True, "kind": "comment", "text": node.get("text") or ""}

    try:
        built = _build_select_for_node(p, node_id)
        sql = built["sql"] + f" LIMIT {max(1, min(int(limit), 200))}"
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Prefer live lake connection for sources / compute
    try:
        from .ai_tools import get_live_connection, run_live_sql
        if get_live_connection():
            res = run_live_sql(sql, limit=limit)
            if isinstance(res, dict) and res.get("ok"):
                return {
                    "ok": True,
                    "kind": "preview",
                    "node_id": node_id,
                    "node_type": node.get("type"),
                    "sql": sql,
                    "columns": res.get("columns") or [],
                    "rows": res.get("rows") or [],
                    "row_count": res.get("row_count") or len(res.get("rows") or []),
                }
            return {"ok": False, "error": (res or {}).get("error") or "query failed", "sql": sql}
    except Exception as e:
        return {"ok": False, "error": str(e), "sql": sql}

    return {"ok": False, "error": "اتصال زنده Postgres نیست — Auto Discovery", "sql": sql}



def materialize_pipeline(pid: int) -> dict:
    """Pull data from lake (live Postgres) and write real tables into warehouse DB."""
    r = get_pipeline(pid)
    if not r.get("ok"):
        return r
    p = r["pipeline"]
    wh = p.get("warehouse") or {}
    if not wh.get("host") or not wh.get("database"):
        return {"ok": False, "error": "اطلاعات warehouse ناقص است (host/database)"}

    schema = wh.get("schema") or "mart"
    try:
        schema = _ident(schema)
    except Exception:
        schema = "mart"

    outputs = [n for n in (p.get("nodes") or []) if n.get("type") == "output"]
    if not outputs:
        return {"ok": False, "error": "هیچ گره Output تعریف نشده"}

    # lake must be available
    try:
        from .ai_tools import get_live_connection, run_live_sql
    except Exception as e:
        return {"ok": False, "error": f"ابزار lake: {e}"}
    if not get_live_connection():
        return {"ok": False, "error": "اتصال دریاچه (Auto Discovery) فعال نیست"}

    try:
        conn = _wh_connect(wh)
        conn.autocommit = True
    except Exception as e:
        return {"ok": False, "error": f"اتصال به warehouse ناموفق: {e}"}

    results = []
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

        for out in outputs:
            target = out.get("target_table") or "pipeline_output"
            try:
                target = _ident(target)
            except Exception as e:
                results.append({"output": str(out.get("target_table")), "ok": False, "error": str(e)})
                continue

            mode = (out.get("load_mode") or p.get("load_mode") or "full").lower()
            try:
                built = _build_select_for_node(p, out["id"])
                select_sql = built["sql"]
            except Exception as e:
                results.append({"output": f"{schema}.{target}", "ok": False, "error": f"compile: {e}"})
                continue

            # Fetch from LAKE (live connection) — full result for materialize
            try:
                import psycopg2
                from psycopg2.extras import RealDictCursor
                li = get_live_connection()
                lconn = psycopg2.connect(
                    host=li["host"], port=int(li["port"] or 5432),
                    dbname=li["name"], user=li["user_name"] or "postgres",
                    password=li["password"] or "", connect_timeout=30,
                )
                lcur = lconn.cursor(cursor_factory=RealDictCursor)
                lcur.execute(select_sql)
                raw_rows = lcur.fetchall()
                cols = [d[0] for d in lcur.description] if lcur.description else []
                rows = [dict(r) for r in raw_rows]
                lcur.close()
                lconn.close()
            except Exception as e:
                results.append({
                    "output": f"{schema}.{target}",
                    "ok": False,
                    "error": f"خواندن از دریاچه: {e}",
                    "sql": select_sql,
                })
                continue
            if not cols:
                results.append({
                    "output": f"{schema}.{target}",
                    "ok": False,
                    "error": "نتیجه بدون ستون",
                    "sql": select_sql,
                })
                continue

            fq = f'"{schema}"."{target}"'
            # quote identifiers for create
            col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
            placeholders = ", ".join(["%s"] * len(cols))
            col_list = ", ".join(f'"{c}"' for c in cols)

            try:
                with conn.cursor() as cur:
                    if mode != "upsert":
                        cur.execute(f"DROP TABLE IF EXISTS {fq}")
                    cur.execute(f"CREATE TABLE IF NOT EXISTS {fq} ({col_defs})")
                    if mode == "full" or mode == "upsert":
                        cur.execute(f"TRUNCATE TABLE {fq}")
                    if rows:
                        values = []
                        for row in rows:
                            values.append([
                                None if row.get(c) is None else str(row.get(c))
                                for c in cols
                            ])
                        cur.executemany(
                            f"INSERT INTO {fq} ({col_list}) VALUES ({placeholders})",
                            values,
                        )
                    cur.execute(f"SELECT COUNT(*) FROM {fq}")
                    cnt = int(cur.fetchone()[0])
                results.append({
                    "output": f"{schema}.{target}",
                    "ok": True,
                    "action": "lake_to_warehouse",
                    "rows": cnt,
                    "columns": cols,
                    "sql": select_sql,
                })
            except Exception as e:
                results.append({
                    "output": f"{schema}.{target}",
                    "ok": False,
                    "error": str(e),
                    "sql": select_sql,
                })
        conn.close()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"ok": False, "error": str(e), "results": results}

    ok_n = sum(1 for x in results if x.get("ok"))
    p.setdefault("runs", [])
    p["runs"] = ([{
        "at": _now(),
        "ok": ok_n == len(results) and ok_n > 0,
        "results": results,
    }] + list(p.get("runs") or []))[:20]
    p["status"] = "ready" if ok_n == len(results) and ok_n > 0 else ("partial" if ok_n else "error")
    p["last_run_at"] = _now()
    save_pipeline(p)

    return {
        "ok": ok_n > 0,
        "materialized": ok_n,
        "total": len(results),
        "results": results,
        "status": p["status"],
    }


def warehouse_properties(pid: int) -> dict:
    """Rich properties page payload."""
    info = pipeline_info(pid)
    if not info.get("ok"):
        return info
    p = info["pipeline"]
    wh = p.get("warehouse") or {}
    outputs = [n for n in (p.get("nodes") or []) if n.get("type") == "output"]
    table_status = []
    schema = wh.get("schema") or "mart"
    try:
        if wh.get("host") and wh.get("database"):
            conn = _wh_connect(wh)
            conn.autocommit = True
            with conn.cursor() as cur:
                for out in outputs:
                    t = out.get("target_table") or "pipeline_output"
                    exists = False
                    rows = None
                    try:
                        cur.execute(
                            """
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema=%s AND table_name=%s
                            """,
                            (schema, t),
                        )
                        exists = cur.fetchone() is not None
                        if exists:
                            cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{t}"')
                            rows = int(cur.fetchone()[0])
                    except Exception as e:
                        table_status.append({
                            "table": f"{schema}.{t}", "exists": False, "error": str(e),
                        })
                        continue
                    table_status.append({
                        "table": f"{schema}.{t}",
                        "exists": exists,
                        "rows": rows,
                        "load_mode": out.get("load_mode") or p.get("load_mode"),
                    })
            conn.close()
    except Exception as e:
        table_status.append({"error": f"warehouse probe failed: {e}"})

    return {
        "ok": True,
        "pipeline": p,
        "stats": info.get("stats"),
        "sql": info.get("sql"),
        "table_status": table_status,
        "runs": (p.get("runs") or [])[:10],
    }
