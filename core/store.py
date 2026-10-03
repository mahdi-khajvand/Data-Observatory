"""
Monitoring metadata store (SQLite) + rich demo seed.
"""
from __future__ import annotations

import json
import random
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .config import DB_PATH

random.seed(42)


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=MEMORY")
        c.execute("PRAGMA synchronous=OFF")
        c.execute("PRAGMA foreign_keys = ON")
    except Exception:
        pass
    try:
        yield c
        c.commit()
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def execute(sql: str, params: tuple = ()) -> None:
    with conn() as c:
        c.execute(sql, params)


def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    with conn() as c:
        rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def fetchone(sql: str, params: tuple = ()) -> Optional[dict]:
    with conn() as c:
        row = c.execute(sql, params).fetchone()
        return dict(row) if row else None


def init_schema() -> None:
    with conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS databases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                db_type TEXT NOT NULL,
                host TEXT,
                port INTEGER,
                status TEXT DEFAULT 'online',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS schemas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                database_id INTEGER NOT NULL,
                schema_name TEXT NOT NULL,
                FOREIGN KEY (database_id) REFERENCES databases(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schema_id INTEGER NOT NULL,
                table_name TEXT NOT NULL,
                row_count INTEGER DEFAULT 0,
                size_bytes INTEGER DEFAULT 0,
                last_update TEXT,
                last_scan TEXT,
                status TEXT DEFAULT 'healthy',
                expected_interval_hours REAL DEFAULT 24,
                sla_hours REAL DEFAULT 26,
                description TEXT DEFAULT '',
                owner TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                created_at TEXT,
                last_schema_change TEXT,
                growth_rate_pct REAL DEFAULT 0,
                FOREIGN KEY (schema_id) REFERENCES schemas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS columns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                column_name TEXT NOT NULL,
                data_type TEXT,
                nullable INTEGER DEFAULT 1,
                ordinal_position INTEGER DEFAULT 0,
                null_pct REAL DEFAULT 0,
                distinct_pct REAL DEFAULT 50,
                example_value TEXT,
                min_val TEXT,
                max_val TEXT,
                mean_val REAL,
                description TEXT DEFAULT '',
                is_pii INTEGER DEFAULT 0,
                is_pk INTEGER DEFAULT 0,
                business_name TEXT DEFAULT '',
                semantic_type TEXT DEFAULT '',
                unit TEXT DEFAULT '',
                synonyms TEXT DEFAULT '',
                business_definition TEXT DEFAULT '',
                calculation_formula TEXT DEFAULT '',
                allowed_values TEXT DEFAULT '',
                is_measure INTEGER DEFAULT 0,
                is_dimension INTEGER DEFAULT 0,
                ai_notes TEXT DEFAULT '',
                FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS table_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                scan_time TEXT,
                row_count INTEGER,
                size_bytes INTEGER,
                last_record_time TEXT,
                FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS schema_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                change_time TEXT,
                change_type TEXT,
                detail TEXT,
                FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS quality_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                check_type TEXT,
                check_time TEXT,
                metric TEXT,
                value REAL,
                threshold REAL,
                status TEXT,
                message TEXT,
                FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER,
                severity TEXT,
                message TEXT,
                created_at TEXT,
                resolved_at TEXT,
                status TEXT DEFAULT 'OPEN'
            );

            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                databases_scanned INTEGER,
                tables_scanned INTEGER,
                status TEXT
            );

            CREATE TABLE IF NOT EXISTS query_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sql_text TEXT,
                engine TEXT,
                row_count INTEGER,
                duration_ms INTEGER,
                status TEXT,
                error TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS health_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER,
                scan_time TEXT,
                overall REAL,
                freshness REAL,
                completeness REAL,
                duplicates REAL,
                schema_score REAL,
                validity REAL,
                volume REAL,
                FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE
            );
            """
        )


# ---------- Demo seed ----------
DEMO_DBS = [
    ("Energy Core", "PostgreSQL", "10.0.1.12", 5432, "online"),
    ("Billing DW", "SQL Server", "10.0.2.40", 1433, "online"),
    ("Analytics Lake", "MySQL", "10.0.3.8", 3306, "online"),
    ("IoT Ingest", "PostgreSQL", "10.0.4.21", 5432, "degraded"),
    ("CRM Mirror", "PostgreSQL", "10.0.5.9", 5432, "online"),
]

DEMO_SCHEMAS = {
    "Energy Core": ["public", "analytics", "staging"],
    "Billing DW": ["dbo", "mart"],
    "Analytics Lake": ["warehouse", "raw"],
    "IoT Ingest": ["public", "sensors"],
    "CRM Mirror": ["public"],
}

TABLE_TEMPLATES = [
    ("MeterData", 82_431_221, 48_000_000_000, 1, "healthy", 1.2),
    ("Billing", 12_400_000, 6_200_000_000, 6, "healthy", 0.4),
    ("MWS_FeederInfo", 24_839_120, 18_400_000_000, 0.3, "healthy", 0.8),
    ("Customer", 1_250_000, 890_000_000, 30, "warning", 0.1),
    ("Events", 91_200_000, 55_000_000_000, 0.5, "healthy", 3.5),
    ("consumption_daily", 8_900_000, 2_100_000_000, 18, "healthy", 1.0),
    ("consumption_monthly", 420_000, 180_000_000, 40, "healthy", 0.2),
    ("Feeder", 3_200_000, 1_400_000_000, 72, "critical", 0.05),
    ("MeterReadings_Raw", 210_000_000, 120_000_000_000, 2, "warning", 4.2),
    ("OutageLog", 890_000, 420_000_000, 12, "healthy", 0.6),
    ("AssetRegistry", 185_000, 95_000_000, 96, "critical", 0.0),
    ("PaymentTx", 45_000_000, 22_000_000_000, 3, "healthy", 1.8),
    ("TariffHistory", 2_100_000, 780_000_000, 20, "healthy", 0.3),
    ("SensorHeartbeat", 500_000_000, 95_000_000_000, 0.2, "healthy", 5.1),
    ("DimDate", 15_000, 2_000_000, 0, "healthy", 0.0),
]

COLUMN_POOL = [
    ("meterId", "varchar(32)", 0, 0.0, 98.0, "11010023456"),
    ("time", "timestamp", 0, 0.0, 99.5, "2026-09-05 19:42:00"),
    ("consumption", "double", 1, 0.2, 83.0, "12.34"),
    ("companyCode", "integer", 0, 0.0, 12.0, "504"),
    ("voltage", "double", 1, 1.1, 70.0, "220.5"),
    ("status", "varchar(16)", 0, 0.0, 4.0, "ACTIVE"),
    ("feeder_id", "varchar(24)", 1, 0.5, 40.0, "FDR-9921"),
    ("region", "varchar(64)", 1, 2.0, 8.0, "Tehran-N"),
    ("amount", "numeric(18,2)", 0, 0.0, 95.0, "145000.00"),
    ("created_at", "timestamp", 0, 0.0, 99.0, "2026-09-01 08:00:00"),
    ("updated_at", "timestamp", 1, 0.3, 88.0, "2026-09-05 12:11:00"),
    ("sourceName", "varchar(64)", 1, 5.0, 15.0, "SCADA-A"),
    ("flag", "boolean", 1, 0.0, 2.0, "true"),
    ("lat", "double", 1, 3.2, 60.0, "35.6892"),
    ("lng", "double", 1, 3.2, 60.0, "51.3890"),
]


def _pick_status(delay_h: float, sla: float) -> str:
    if delay_h <= sla * 0.5:
        return "healthy"
    if delay_h <= sla:
        return "warning"
    return "critical"


def _migrate() -> None:
    """Add new columns if upgrading from older DB."""
    with conn() as c:
        cols_t = {r[1] for r in c.execute("PRAGMA table_info(tables)").fetchall()}
        if "description" not in cols_t:
            c.execute("ALTER TABLE tables ADD COLUMN description TEXT DEFAULT ''")
        if "owner" not in cols_t:
            c.execute("ALTER TABLE tables ADD COLUMN owner TEXT DEFAULT ''")
        if "tags" not in cols_t:
            c.execute("ALTER TABLE tables ADD COLUMN tags TEXT DEFAULT ''")
        cols_c = {r[1] for r in c.execute("PRAGMA table_info(columns)").fetchall()}
        if "description" not in cols_c:
            c.execute("ALTER TABLE columns ADD COLUMN description TEXT DEFAULT ''")
        if "is_pii" not in cols_c:
            c.execute("ALTER TABLE columns ADD COLUMN is_pii INTEGER DEFAULT 0")
        if "is_pk" not in cols_c:
            c.execute("ALTER TABLE columns ADD COLUMN is_pk INTEGER DEFAULT 0")
        # Rich AI-oriented column metadata (stored on columns table for FK integrity)
        for col, ddl in [
            ("business_name", "TEXT DEFAULT ''"),
            ("semantic_type", "TEXT DEFAULT ''"),
            ("unit", "TEXT DEFAULT ''"),
            ("synonyms", "TEXT DEFAULT ''"),  # comma-separated or JSON array string
            ("business_definition", "TEXT DEFAULT ''"),
            ("calculation_formula", "TEXT DEFAULT ''"),
            ("allowed_values", "TEXT DEFAULT ''"),  # comma-separated or JSON
            ("is_measure", "INTEGER DEFAULT 0"),
            ("is_dimension", "INTEGER DEFAULT 0"),
            ("ai_notes", "TEXT DEFAULT ''"),
        ]:
            if col not in cols_c:
                c.execute(f"ALTER TABLE columns ADD COLUMN {col} {ddl}")
                cols_c.add(col)


def seed_if_empty() -> None:

    init_schema()
    existing = fetchone("SELECT COUNT(*) AS c FROM databases")
    if existing and existing["c"] > 0:
        return

    now = utc_now()
    with conn() as c:
        db_ids = {}
        for name, typ, host, port, status in DEMO_DBS:
            cur = c.execute(
                "INSERT INTO databases (name, db_type, host, port, status, created_at) VALUES (?,?,?,?,?,?)",
                (name, typ, host, port, status, iso(now - timedelta(days=random.randint(60, 400)))),
            )
            db_ids[name] = cur.lastrowid

        schema_ids = {}
        for db_name, schemas in DEMO_SCHEMAS.items():
            for sn in schemas:
                cur = c.execute(
                    "INSERT INTO schemas (database_id, schema_name) VALUES (?,?)",
                    (db_ids[db_name], sn),
                )
                schema_ids[(db_name, sn)] = cur.lastrowid

        # distribute tables across schemas
        schema_list = list(schema_ids.items())
        table_ids = []
        for i, (tname, rows, size_b, delay_h, base_status, growth) in enumerate(TABLE_TEMPLATES):
            (db_name, sn), sid = schema_list[i % len(schema_list)]
            last_upd = now - timedelta(hours=delay_h)
            sla = 2.0 if "Meter" in tname or "Sensor" in tname or "Events" in tname else 26.0
            interval = 1.0 if sla <= 3 else 24.0
            status = _pick_status(delay_h, sla)
            created = now - timedelta(days=random.randint(120, 900))
            schema_chg = now - timedelta(days=random.randint(5, 60)) if random.random() > 0.5 else None
            cur = c.execute(
                """INSERT INTO tables
                (schema_id, table_name, row_count, size_bytes, last_update, last_scan,
                 status, expected_interval_hours, sla_hours, created_at, last_schema_change, growth_rate_pct)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sid,
                    tname,
                    rows,
                    size_b,
                    iso(last_upd),
                    iso(now - timedelta(minutes=random.randint(2, 40))),
                    status,
                    interval,
                    sla,
                    iso(created),
                    iso(schema_chg) if schema_chg else None,
                    growth,
                ),
            )
            tid = cur.lastrowid
            table_ids.append((tid, tname, rows, size_b, delay_h, status, growth))

            # columns
            ncols = random.randint(6, 14)
            cols = random.sample(COLUMN_POOL, min(ncols, len(COLUMN_POOL)))
            for oi, col in enumerate(cols):
                cname, dtype, nullable, null_pct, dist_pct, example = col
                # inject some quality issues
                if status == "critical" and cname == "consumption":
                    null_pct = 8.7
                if tname == "MeterData" and cname == "meterId":
                    null_pct = 0.01
                c.execute(
                    """INSERT INTO columns
                    (table_id, column_name, data_type, nullable, ordinal_position,
                     null_pct, distinct_pct, example_value, min_val, max_val, mean_val)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        tid,
                        cname,
                        dtype,
                        nullable,
                        oi + 1,
                        null_pct,
                        dist_pct,
                        example,
                        "0" if "double" in dtype or "numeric" in dtype else None,
                        "48923" if cname == "consumption" else None,
                        14.82 if cname == "consumption" else None,
                    ),
                )

            # snapshots (growth history) last 30 days
            for d in range(30, -1, -1):
                day = now - timedelta(days=d)
                factor = 1 - (growth / 100) * (d / 7)
                rc = int(rows * max(0.7, factor) * (0.98 + random.random() * 0.04))
                sz = int(size_b * max(0.7, factor))
                c.execute(
                    """INSERT INTO table_snapshots
                    (table_id, scan_time, row_count, size_bytes, last_record_time)
                    VALUES (?,?,?,?,?)""",
                    (tid, iso(day.replace(hour=6, minute=0)), rc, sz, iso(day - timedelta(hours=random.randint(0, 12)))),
                )

            # schema history
            if schema_chg:
                c.execute(
                    "INSERT INTO schema_history (table_id, change_time, change_type, detail) VALUES (?,?,?,?)",
                    (tid, iso(schema_chg), "ADD_COLUMN", "+ sourceName varchar(64)"),
                )
            if random.random() > 0.7:
                c.execute(
                    "INSERT INTO schema_history (table_id, change_time, change_type, detail) VALUES (?,?,?,?)",
                    (
                        tid,
                        iso(now - timedelta(days=random.randint(70, 200))),
                        "TYPE_CHANGE",
                        "consumption: double precision → numeric(18,4)",
                    ),
                )

            # quality results
            checks = [
                ("null_check", "null_rate", 0.2 if status != "critical" else 8.7, 5.0),
                ("duplicate_check", "duplicate_count", 1283 if tname == "MeterData" else random.randint(0, 200), 100),
                ("range_check", "invalid_records", 2381 if status == "critical" else random.randint(0, 50), 100),
                ("freshness_check", "delay_hours", delay_h, sla),
                ("uniqueness_check", "unique_pct", 99.1, 95.0),
            ]
            for ctype, metric, val, thr in checks:
                st = "PASS"
                if ctype == "null_check" and val > thr:
                    st = "FAIL"
                elif ctype == "duplicate_check" and val > thr:
                    st = "FAIL"
                elif ctype == "range_check" and val > thr:
                    st = "FAIL"
                elif ctype == "freshness_check" and val > thr:
                    st = "FAIL"
                elif ctype == "freshness_check" and val > thr * 0.5:
                    st = "WARN"
                c.execute(
                    """INSERT INTO quality_results
                    (table_id, check_type, check_time, metric, value, threshold, status, message)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        tid,
                        ctype,
                        iso(now - timedelta(minutes=random.randint(5, 90))),
                        metric,
                        val,
                        thr,
                        st,
                        f"{ctype}: {metric}={val}",
                    ),
                )

            # health scores
            freshness_s = max(0, 100 - delay_h * (8 if interval <= 2 else 2))
            completeness = max(60, 100 - (8.7 if status == "critical" else 0.5) * 4)
            duplicates_s = 91 if tname == "MeterData" else random.randint(88, 100)
            schema_s = 100 if not schema_chg or (now - schema_chg).days > 14 else 85
            validity = 82 if status == "critical" else random.randint(90, 100)
            volume_s = random.randint(88, 99)
            overall = round(
                (freshness_s * 0.25 + completeness * 0.2 + duplicates_s * 0.15 + schema_s * 0.15 + validity * 0.15 + volume_s * 0.1),
                1,
            )
            c.execute(
                """INSERT INTO health_scores
                (table_id, scan_time, overall, freshness, completeness, duplicates, schema_score, validity, volume)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (tid, iso(now), overall, freshness_s, completeness, duplicates_s, schema_s, validity, volume_s),
            )

        # alerts
        alert_msgs = [
            ("CRITICAL", "MeterData hasn't been updated for 9 hours."),
            ("WARNING", "Billing update delayed by 2 hours."),
            ("CRITICAL", "consumption NULL rate increased from 0.2% → 8.7%"),
            ("WARNING", "MeterData row growth dropped by 73%."),
            ("CRITICAL", "Feeder table stale for 72 hours — SLA breached."),
            ("WARNING", "Customer dimension delayed 27h."),
            ("INFO", "Schema change detected on MWS_FeederInfo (+ sourceName)."),
            ("CRITICAL", "AssetRegistry no updates for 4 days."),
        ]
        for sev, msg in alert_msgs:
            tid = table_ids[random.randint(0, len(table_ids) - 1)][0]
            c.execute(
                "INSERT INTO alerts (table_id, severity, message, created_at, status) VALUES (?,?,?,?,?)",
                (tid, sev, msg, iso(now - timedelta(hours=random.randint(1, 48))), "OPEN"),
            )

        c.execute(
            "INSERT INTO scans (started_at, finished_at, databases_scanned, tables_scanned, status) VALUES (?,?,?,?,?)",
            (iso(now - timedelta(minutes=8)), iso(now - timedelta(minutes=5)), len(DEMO_DBS), len(TABLE_TEMPLATES), "success"),
        )




def clear_all_catalog() -> None:
    """Remove all demo/catalog data (keep schema)."""
    with conn() as c:
        for tbl in (
            "query_history", "alerts", "health_scores", "quality_results",
            "schema_history", "table_snapshots", "columns", "tables",
            "schemas", "databases", "scans",
        ):
            try:
                c.execute(f"DELETE FROM {tbl}")
            except Exception:
                pass


def ensure_db(seed: bool = False) -> None:
    init_schema()
    try:
        _migrate()
    except Exception:
        pass
    if seed:
        try:
            seed_if_empty()
        except Exception:
            pass


def ensure_workspace_tables() -> None:
    """BI dashboards + ML notebooks persistence."""
    with conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS bi_dashboards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT,
                created_at TEXT
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS ml_notebooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                table_name TEXT,
                cells_json TEXT NOT NULL,
                updated_at TEXT,
                created_at TEXT
            )"""
        )
