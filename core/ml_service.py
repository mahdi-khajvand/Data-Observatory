"""
Machine Learning Studio — جدا از بقیه سیستم.
جدول اصلی را تغییر نمی‌دهد؛ VIEW و/یا dataset محلی تمیز می‌سازد.
"""
from __future__ import annotations

import json
import math
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import store
from .config import DATA_DIR
from .ai_tools import get_live_connection, run_live_sql, execute_tool


def _json_safe(obj):
    """تبدیل NaN/Inf و numpy types برای JSON."""
    import math
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        x = float(obj)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return _json_safe(obj.tolist())
    return obj


ML_DIR = DATA_DIR / "ml"
ML_DIR.mkdir(parents=True, exist_ok=True)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _ensure_ml_tables():
    store.execute(
        """CREATE TABLE IF NOT EXISTS ml_experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            table_name TEXT,
            target_col TEXT,
            task_type TEXT,
            model_name TEXT,
            view_name TEXT,
            dataset_path TEXT,
            metrics_json TEXT,
            params_json TEXT,
            feature_list TEXT,
            preprocess_json TEXT,
            status TEXT DEFAULT 'created',
            notes TEXT,
            created_at TEXT,
            model_path TEXT,
            analysis_text TEXT,
            predictions_json TEXT
        )"""
    )
    # migrate older DBs
    for col, typ in [
        ("model_path", "TEXT"),
        ("analysis_text", "TEXT"),
        ("predictions_json", "TEXT"),
    ]:
        try:
            store.execute(f"ALTER TABLE ml_experiments ADD COLUMN {col} {typ}")
        except Exception:
            pass


def list_catalog_tables() -> dict:
    rows = store.fetchall(
        """SELECT t.id, t.table_name, t.row_count, t.status,
                  s.schema_name, d.name AS db_name
           FROM tables t
           JOIN schemas s ON s.id=t.schema_id
           JOIN databases d ON d.id=s.database_id
           ORDER BY d.name, t.table_name"""
    )
    return {
        "tables": [
            {
                "table_id": r["id"],
                "table": r["table_name"],
                "schema": r["schema_name"],
                "db": r["db_name"],
                "rows": r["row_count"],
                "status": r["status"],
            }
            for r in rows
        ]
    }


def _fetch_frame(table_name: str, limit: int = 5000) -> Tuple[Optional["object"], Optional[str]]:
    """خواندن داده از Postgres زنده به pandas."""
    try:
        import pandas as pd
    except ImportError:
        return None, "pandas نصب نیست"

    conn = get_live_connection()
    if not conn or not conn.get("host"):
        return None, "اتصال زنده Postgres ثبت نشده — اول Auto Discovery بزن."

    # sanitize table name
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table_name or ""):
        return None, "نام جدول نامعتبر است"

    sql = f'SELECT * FROM "{table_name}" LIMIT {int(limit)}'
    res = run_live_sql(sql, limit=limit)
    if not res.get("ok"):
        # try without quotes
        sql2 = f"SELECT * FROM {table_name} LIMIT {int(limit)}"
        res = run_live_sql(sql2, limit=limit)
    if not res.get("ok"):
        return None, res.get("error") or "خواندن جدول ناموفق"

    rows = res.get("rows") or []
    if not rows:
        return pd.DataFrame(), None
    df = pd.DataFrame(rows)
    return df, None


def profile_table(table_name: str, table_id: Optional[int] = None, sample_limit: int = 3000) -> dict:
    """پروفایل جدول + متادیتا برای پیشنهاد ML."""
    meta = None
    if table_id:
        meta = execute_tool("get_table_metadata", {"table_id": int(table_id)})
    if not meta or meta.get("error"):
        meta = execute_tool("get_table_metadata", {"table_name": table_name})

    df, err = _fetch_frame(table_name, limit=sample_limit)
    if err and df is None:
        return {"ok": False, "error": err}

    import pandas as pd

    if df is None:
        df = pd.DataFrame()

    cols_info = []
    for c in df.columns:
        s = df[c]
        null_pct = float(s.isna().mean() * 100) if len(s) else 0
        nunique = int(s.nunique(dropna=True))
        dtype = str(s.dtype)
        sample = []
        for v in s.dropna().head(5).tolist():
            sample.append(str(v)[:80])
        numeric = pd.api.types.is_numeric_dtype(s)
        stats = {}
        if numeric and s.notna().any():
            stats = {
                "min": float(s.min()),
                "max": float(s.max()),
                "mean": float(s.mean()),
                "std": float(s.std()) if s.notna().sum() > 1 else 0,
            }
        # metadata enrich
        mcol = None
        for mc in (meta or {}).get("columns") or []:
            if (mc.get("name") or "").lower() == str(c).lower():
                mcol = mc
                break
        cols_info.append({
            "name": str(c),
            "dtype": dtype,
            "null_pct": round(null_pct, 2),
            "nunique": nunique,
            "is_numeric": bool(numeric),
            "sample": sample,
            "stats": stats,
            "business_name": (mcol or {}).get("business_name") or "",
            "semantic_type": (mcol or {}).get("semantic_type") or "",
            "is_measure": bool((mcol or {}).get("is_measure")),
            "is_dimension": bool((mcol or {}).get("is_dimension")),
            "unit": (mcol or {}).get("unit") or "",
        })

    # heuristic target suggestions
    suggestions = _suggest_targets(cols_info, meta)

    return {
        "ok": True,
        "table": table_name,
        "table_id": table_id,
        "n_rows_sampled": int(len(df)),
        "n_cols": int(df.shape[1]) if df is not None else 0,
        "columns": cols_info,
        "metadata": {
            "description": (meta or {}).get("description"),
            "measures": (meta or {}).get("measures"),
            "dimensions": (meta or {}).get("dimensions"),
        },
        "target_suggestions": suggestions,
        "preprocess_suggestions": _suggest_preprocess(cols_info),
        "model_suggestions": _suggest_models(suggestions),
    }


def _suggest_targets(cols_info: list, meta: Optional[dict]) -> list:
    out = []
    for c in cols_info:
        name = c["name"]
        low = name.lower()
        score = 0
        reasons = []
        if c.get("is_measure"):
            score += 3
            reasons.append("متادیتا: measure")
        if any(k in low for k in ("target", "label", "y_", "outcome", "churn", "default")):
            score += 4
            reasons.append("نام شبیه target")
        if any(k in low for k in ("net_income", "revenue", "profit", "price", "amount", "score", "rate", "margin", "roe", "roa")):
            score += 2
            reasons.append("شاخص کسب‌وکار رایج")
        if c["is_numeric"] and c["nunique"] > 5 and c["null_pct"] < 40:
            score += 1
        if c["nunique"] == 2:
            score += 2
            reasons.append("دودویی → classification")
            task = "classification"
        elif c["is_numeric"] and c["nunique"] > 10:
            task = "regression"
        elif 2 < c["nunique"] <= 20 and not c["is_numeric"]:
            task = "classification"
            score += 1
        else:
            task = "regression" if c["is_numeric"] else "classification"

        # skip ids
        if low in ("id", "pk") or low.endswith("_id"):
            score -= 5
            reasons.append("احتمالاً شناسه")

        if score >= 2:
            out.append({
                "column": name,
                "task": task,
                "score": score,
                "reasons": reasons,
                "business_name": c.get("business_name") or name,
            })
    out.sort(key=lambda x: -x["score"])
    return out[:8]


def _suggest_preprocess(cols_info: list) -> list:
    steps = []
    high_null = [c["name"] for c in cols_info if c["null_pct"] >= 60]
    mid_null = [c["name"] for c in cols_info if 5 <= c["null_pct"] < 60]
    ids = [c["name"] for c in cols_info if c["name"].lower() in ("id",) or c["name"].lower().endswith("_id")]
    cats = [c["name"] for c in cols_info if (not c["is_numeric"]) and c["nunique"] <= 30]
    high_card = [c["name"] for c in cols_info if (not c["is_numeric"]) and c["nunique"] > 50]

    if ids:
        steps.append({"action": "drop_columns", "columns": ids, "reason": "شناسه‌ها معمولاً برای مدل مفید نیستند"})
    if high_null:
        steps.append({"action": "drop_columns", "columns": high_null, "reason": "بیش از ۶۰٪ مقدار خالی"})
    if mid_null:
        steps.append({"action": "impute_median_or_mode", "columns": mid_null, "reason": "پر کردن null برای آموزش پایدار"})
    if cats:
        steps.append({"action": "one_hot_or_label_encode", "columns": cats, "reason": "کدگذاری ویژگی‌های دسته‌ای"})
    if high_card:
        steps.append({"action": "drop_or_hash_encode", "columns": high_card, "reason": "کاردینالیتی بالا"})
    steps.append({"action": "train_test_split", "params": {"test_size": 0.2, "random_state": 42}, "reason": "ارزیابی عادلانه"})
    return steps


def _suggest_models(target_suggestions: list) -> list:
    task = (target_suggestions[0]["task"] if target_suggestions else "regression")
    if task == "classification":
        models = [
            {"name": "RandomForestClassifier", "why": "قوی، مقاوم به نویز، بدون نیاز زیاد به اسکیل"},
            {"name": "GradientBoostingClassifier", "why": "دقت بالا روی داده جدولی"},
            {"name": "LogisticRegression", "why": "پایه و قابل‌تفسیر"},
            {"name": "XGBoostClassifier", "why": "اغلب بهترین روی tabular — اگر نصب باشد"},
        ]
    else:
        models = [
            {"name": "RandomForestRegressor", "why": "قوی و پایدار برای رگرسیون جدولی"},
            {"name": "GradientBoostingRegressor", "why": "دقت خوب روی روابط غیرخطی"},
            {"name": "Ridge", "why": "سریع و قابل‌تفسیر"},
            {"name": "XGBoostRegressor", "why": "اغلب SOTA روی tabular — اگر نصب باشد"},
        ]
    return {"task": task, "models": models}


def ai_advise_table(table_name: str, table_id: Optional[int] = None) -> dict:
    """پروفایل + تحلیل LLM برای پیشنهاد target و پیش‌پردازش."""
    profile = profile_table(table_name, table_id=table_id)
    if not profile.get("ok"):
        return profile

    analysis_text = ""
    try:
        from .ai_service import DEFAULT_MODEL, OLLAMA_HOST, SYSTEM
        import ollama
        client = ollama.Client(host=OLLAMA_HOST) if OLLAMA_HOST else ollama
        compact = {
            "table": profile["table"],
            "n_rows": profile["n_rows_sampled"],
            "columns": [
                {
                    "name": c["name"],
                    "dtype": c["dtype"],
                    "null_pct": c["null_pct"],
                    "nunique": c["nunique"],
                    "is_numeric": c["is_numeric"],
                    "business_name": c.get("business_name"),
                    "semantic_type": c.get("semantic_type"),
                    "is_measure": c.get("is_measure"),
                }
                for c in profile["columns"]
            ],
            "target_suggestions": profile["target_suggestions"],
            "preprocess_suggestions": profile["preprocess_suggestions"],
            "model_suggestions": profile["model_suggestions"],
            "metadata": profile.get("metadata"),
        }
        resp = client.chat(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "تو مشاور ML برای داده جدولی هستی. فارسی، دقیق، عملی بنویس. "
                        "هدف پیش‌بینی، ویژگی‌های مهم، پیش‌پردازش لازم و مدل‌های پیشنهادی را مشخص کن. "
                        "عدد جعلی نساز."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"جدول `{table_name}` را برای ساخت مدل بررسی کن:\n"
                        + json.dumps(compact, ensure_ascii=False, default=str)[:12000]
                        + "\n\nخروجی: ۱) چه چیزی قابل پیش‌بینی است ۲) target پیشنهادی "
                        "۳) پیش‌پردازش ۴) مدل‌های مناسب ۵) ریسک‌ها"
                    ),
                },
            ],
            options={"temperature": 0.3, "num_predict": 1600},
        )
        msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", {})
        analysis_text = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
    except Exception as e:
        # heuristic fallback
        ts = profile["target_suggestions"]
        analysis_text = (
            f"## بررسی جدول `{table_name}`\n\n"
            f"نمونه: **{profile['n_rows_sampled']}** ردیف · **{profile['n_cols']}** ستون\n\n"
        )
        if ts:
            analysis_text += "### هدف‌های پیشنهادی\n"
            for t in ts[:5]:
                analysis_text += f"- **{t['column']}** ({t['task']}) — score {t['score']}: {', '.join(t['reasons'])}\n"
        analysis_text += "\n### پیش‌پردازش\n"
        for s in profile["preprocess_suggestions"]:
            analysis_text += f"- `{s['action']}`: {s.get('reason','')}\n"
        analysis_text += f"\n_(تحلیل LLM در دسترس نبود: {e})_"

    profile["ai_analysis"] = analysis_text
    return profile


def build_clean_dataset(
    table_name: str,
    target_col: str,
    feature_cols: Optional[List[str]] = None,
    drop_cols: Optional[List[str]] = None,
    create_sql_view: bool = True,
    sample_limit: int = 10000,
) -> dict:
    """
    ساخت dataset تمیز محلی + (اختیاری) VIEW فقط‌خواندنی روی Postgres.
    جدول اصلی دست نخورده می‌ماند.
    """
    import pandas as pd

    df, err = _fetch_frame(table_name, limit=sample_limit)
    if err:
        return {"ok": False, "error": err}
    if df is None or df.empty:
        return {"ok": False, "error": "داده خالی است"}

    if target_col not in df.columns:
        return {"ok": False, "error": f"ستون هدف یافت نشد: {target_col}"}

    drop_cols = list(drop_cols or [])
    # auto drop id-like if not specified
    for c in list(df.columns):
        if c == target_col:
            continue
        if c.lower() == "id" or c.lower().endswith("_id"):
            if c not in drop_cols:
                drop_cols.append(c)

    work = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")

    if feature_cols:
        keep = [c for c in feature_cols if c in work.columns and c != target_col]
        keep.append(target_col)
        work = work[keep]

    # drop rows with null target
    work = work.dropna(subset=[target_col])

    # impute numeric median / categorical mode
    for c in work.columns:
        if c == target_col:
            continue
        if pd.api.types.is_numeric_dtype(work[c]):
            med = work[c].median()
            work[c] = work[c].fillna(med)
        else:
            mode = work[c].mode()
            fill = mode.iloc[0] if len(mode) else ""
            work[c] = work[c].fillna(fill)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_t = re.sub(r"[^a-zA-Z0-9_]", "_", table_name)[:40]
    path = ML_DIR / f"clean_{safe_t}_{ts}.csv"
    work.to_csv(path, index=False)

    view_name = None
    view_sql = None
    view_error = None
    if create_sql_view:
        view_name = f"ml_view_{safe_t}_{ts}"
        cols = ", ".join(f'"{c}"' for c in work.columns)
        # VIEW only projects columns present in source (imputed values stay in local CSV)
        src_cols = [c for c in work.columns if c in df.columns]
        cols_src = ", ".join(f'"{c}"' for c in src_cols)
        view_sql = f'CREATE OR REPLACE VIEW "{view_name}" AS SELECT {cols_src} FROM "{table_name}"'
        try:
            conn = get_live_connection()
            if conn and conn.get("host"):
                import psycopg2
                pg = psycopg2.connect(
                    host=conn["host"],
                    port=int(conn["port"] or 5432),
                    dbname=conn["name"],
                    user=conn["user_name"] or "postgres",
                    password=conn["password"] or "",
                    connect_timeout=12,
                )
                cur = pg.cursor()
                cur.execute(view_sql)
                pg.commit()
                cur.close()
                pg.close()
            else:
                view_error = "بدون اتصال زنده — فقط CSV محلی ساخته شد"
                view_name = None
        except Exception as e:
            view_error = str(e)
            view_name = None

    _ensure_ml_tables()
    store.execute(
        """INSERT INTO ml_experiments
           (name, table_name, target_col, task_type, model_name, view_name, dataset_path,
            metrics_json, params_json, feature_list, preprocess_json, status, notes, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"prep_{safe_t}",
            table_name,
            target_col,
            "",
            "",
            view_name or "",
            str(path),
            "",
            "",
            json.dumps([c for c in work.columns if c != target_col]),
            json.dumps({"drop_cols": drop_cols, "imputed": True}),
            "prepared",
            view_error or "",
            _utc(),
        ),
    )
    exp_id = store.fetchone("SELECT id FROM ml_experiments ORDER BY id DESC LIMIT 1")["id"]

    return {
        "ok": True,
        "experiment_id": exp_id,
        "dataset_path": str(path),
        "n_rows": int(len(work)),
        "n_features": int(work.shape[1] - 1),
        "columns": list(work.columns),
        "view_name": view_name,
        "view_sql": view_sql,
        "view_error": view_error,
        "note": "جدول اصلی تغییر نکرد. داده تمیز در CSV محلی ذخیره شد.",
    }


def _get_estimator(model_name: str, task: str):
    from sklearn.ensemble import (
        RandomForestClassifier, RandomForestRegressor,
        GradientBoostingClassifier, GradientBoostingRegressor,
    )
    from sklearn.linear_model import LogisticRegression, Ridge

    name = (model_name or "").lower()
    if task == "classification":
        if "xgb" in name:
            try:
                from xgboost import XGBClassifier
                return XGBClassifier(
                    n_estimators=100, max_depth=4, learning_rate=0.1,
                    subsample=0.9, colsample_bytree=0.9,
                    eval_metric="logloss", random_state=42, n_jobs=-1,
                ), {
                    "n_estimators": [80, 120],
                    "max_depth": [3, 5],
                    "learning_rate": [0.05, 0.1],
                }
            except ImportError:
                pass
        if "logistic" in name:
            return LogisticRegression(max_iter=500, random_state=42), {
                "C": [0.1, 1.0, 10.0],
            }
        if "gradient" in name or "gb" in name:
            return GradientBoostingClassifier(random_state=42), {
                "n_estimators": [80, 120],
                "max_depth": [2, 3],
                "learning_rate": [0.05, 0.1],
            }
        return RandomForestClassifier(random_state=42, n_jobs=-1), {
            "n_estimators": [100, 200],
            "max_depth": [None, 8, 16],
            "min_samples_leaf": [1, 2],
        }
    else:
        if "xgb" in name:
            try:
                from xgboost import XGBRegressor
                return XGBRegressor(
                    n_estimators=100, max_depth=4, learning_rate=0.1,
                    subsample=0.9, colsample_bytree=0.9,
                    random_state=42, n_jobs=-1,
                ), {
                    "n_estimators": [80, 120],
                    "max_depth": [3, 5],
                    "learning_rate": [0.05, 0.1],
                }
            except ImportError:
                pass
        if "ridge" in name:
            return Ridge(), {"alpha": [0.1, 1.0, 10.0]}
        if "gradient" in name or "gb" in name:
            return GradientBoostingRegressor(random_state=42), {
                "n_estimators": [80, 120],
                "max_depth": [2, 3],
                "learning_rate": [0.05, 0.1],
            }
        return RandomForestRegressor(random_state=42, n_jobs=-1), {
            "n_estimators": [100, 200],
            "max_depth": [None, 8, 16],
            "min_samples_leaf": [1, 2],
        }


def train_model(
    dataset_path: str,
    target_col: str,
    model_name: str = "RandomForest",
    task_type: Optional[str] = None,
    test_size: float = 0.2,
    grid_search: bool = True,
    experiment_id: Optional[int] = None,
) -> dict:
    """آموزش با GridSearch روی dataset تمیز محلی."""
    import pandas as pd
    from sklearn.model_selection import train_test_split, GridSearchCV
    from sklearn.preprocessing import LabelEncoder
    from sklearn.metrics import (
        accuracy_score, f1_score, r2_score, mean_absolute_error, mean_squared_error,
        classification_report,
    )

    path = Path(dataset_path)
    if not path.exists():
        return {"ok": False, "error": f"فایل dataset نیست: {dataset_path}"}

    df = pd.read_csv(path)
    if target_col not in df.columns:
        return {"ok": False, "error": f"target نیست: {target_col}"}

    y_raw = df[target_col]
    X = df.drop(columns=[target_col])

    # encode categoricals
    cat_maps = {}
    for c in list(X.columns):
        if not pd.api.types.is_numeric_dtype(X[c]):
            le = LabelEncoder()
            X[c] = le.fit_transform(X[c].astype(str))
            cat_maps[c] = list(le.classes_)

    # detect task
    if not task_type:
        if not pd.api.types.is_numeric_dtype(y_raw) or y_raw.nunique() <= 15:
            task_type = "classification"
        else:
            task_type = "regression"

    y = y_raw
    label_encoder = None
    if task_type == "classification":
        label_encoder = LabelEncoder()
        y = label_encoder.fit_transform(y_raw.astype(str))

    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=float(test_size), random_state=42,
            stratify=y if task_type == "classification" and len(set(y)) > 1 else None,
        )
    except Exception:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=float(test_size), random_state=42,
        )

    est, param_grid = _get_estimator(model_name, task_type)
    best_params = {}
    cv_score = None

    if grid_search and param_grid:
        scoring = "f1_weighted" if task_type == "classification" else "r2"
        try:
            gs = GridSearchCV(est, param_grid, cv=min(3, max(2, len(X_train) // 5)), scoring=scoring, n_jobs=-1)
            gs.fit(X_train, y_train)
            model = gs.best_estimator_
            best_params = gs.best_params_
            cv_score = float(gs.best_score_)
        except Exception as e:
            model = est
            model.fit(X_train, y_train)
            best_params = {"grid_search_error": str(e)}
    else:
        model = est
        model.fit(X_train, y_train)

    pred = model.predict(X_test)
    metrics = {}
    report = ""
    if task_type == "classification":
        metrics = {
            "accuracy": float(accuracy_score(y_test, pred)),
            "f1_weighted": float(f1_score(y_test, pred, average="weighted", zero_division=0)),
        }
        try:
            report = classification_report(y_test, pred, zero_division=0)
        except Exception:
            report = ""
    else:
        def _f(x):
            try:
                x = float(x)
                return None if (math.isnan(x) or math.isinf(x)) else x
            except Exception:
                return None
        metrics = {
            "r2": _f(r2_score(y_test, pred)),
            "mae": _f(mean_absolute_error(y_test, pred)),
            "rmse": _f(math.sqrt(mean_squared_error(y_test, pred))),
        }

    if cv_score is not None:
        metrics["cv_best_score"] = cv_score

    # feature importance
    importances = []
    if hasattr(model, "feature_importances_"):
        for name, imp in sorted(zip(X.columns, model.feature_importances_), key=lambda x: -x[1]):
            importances.append({"feature": str(name), "importance": (None if (isinstance(imp, float) and (math.isnan(imp) or math.isinf(imp))) else float(imp))})
    elif hasattr(model, "coef_"):
        coef = np.ravel(model.coef_)
        for name, imp in sorted(zip(X.columns, np.abs(coef)), key=lambda x: -x[1]):
            importances.append({"feature": str(name), "importance": (None if (isinstance(imp, float) and (math.isnan(imp) or math.isinf(imp))) else float(imp))})

    # quality verdict
    if task_type == "classification":
        score = metrics.get("f1_weighted") or metrics.get("accuracy") or 0
        verdict = "خوب" if score >= 0.75 else ("متوسط" if score >= 0.55 else "ضعیف — نیاز به feature engineering")
    else:
        score = metrics.get("r2") or 0
        verdict = "خوب" if score >= 0.7 else ("متوسط" if score >= 0.4 else "ضعیف — نیاز به feature engineering")

    metrics["verdict"] = verdict

    # persist model
    model_path = None
    try:
        import joblib
        mp = ML_DIR / f"model_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.joblib"
        joblib.dump({
            "model": model,
            "target": target_col,
            "task": task_type,
            "features": list(X.columns),
            "cat_maps": cat_maps,
            "label_classes": list(label_encoder.classes_) if label_encoder is not None else None,
        }, mp)
        model_path = str(mp)
    except Exception:
        pass

    # AI narrative + predictions before persist
    narrative = _train_narrative(model_name, task_type, metrics, importances, best_params)
    pred_payload = {}
    try:
        yt = list(y_test) if hasattr(y_test, '__iter__') else []
        yp = list(pred) if hasattr(pred, '__iter__') else []
        n = min(80, len(yp))
        pred_payload = {
            "y_true": [float(x) if not isinstance(x, (str, bytes)) else str(x) for x in yt[:n]],
            "y_pred": [float(x) if not isinstance(x, (str, bytes)) else str(x) for x in yp[:n]],
        }
    except Exception:
        pred_payload = {}

    _ensure_ml_tables()
    if experiment_id:
        store.execute(
            """UPDATE ml_experiments SET model_name=?, task_type=?, metrics_json=?, params_json=?,
               feature_list=?, status=?, notes=?, name=?, model_path=?, analysis_text=?, predictions_json=?,
               dataset_path=COALESCE(NULLIF(dataset_path,''), ?) WHERE id=?""",
            (
                model_name,
                task_type,
                json.dumps(metrics),
                json.dumps(best_params),
                json.dumps(list(X.columns)),
                "trained",
                verdict,
                f"{model_name}_{target_col}",
                model_path or "",
                narrative,
                json.dumps(pred_payload),
                dataset_path or "",
                int(experiment_id),
            ),
        )
    else:
        store.execute(
            """INSERT INTO ml_experiments
               (name, table_name, target_col, task_type, model_name, view_name, dataset_path,
                metrics_json, params_json, feature_list, preprocess_json, status, notes, created_at,
                model_path, analysis_text, predictions_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"{model_name}_{target_col}",
                "",
                target_col,
                task_type,
                model_name,
                "",
                dataset_path,
                json.dumps(metrics),
                json.dumps(best_params),
                json.dumps(list(X.columns)),
                "",
                "trained",
                verdict,
                _utc(),
                model_path or "",
                narrative,
                json.dumps(pred_payload),
            ),
        )
        experiment_id = store.fetchone("SELECT id FROM ml_experiments ORDER BY id DESC LIMIT 1")["id"]

    return _json_safe({
        "ok": True,
        "experiment_id": experiment_id,
        "task_type": task_type,
        "model_name": model_name,
        "metrics": metrics,
        "best_params": best_params,
        "feature_importance": importances[:20],
        "classification_report": report,
        "model_path": model_path,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "n_features": int(X.shape[1]),
        "analysis": narrative,
        "predictions": pred_payload,
        "target_col": target_col,
        "features": list(X.columns),
        "dataset_path": dataset_path,
    })


def _train_narrative(model_name, task, metrics, importances, params) -> str:
    lines = [
        f"## نتیجه آموزش `{model_name}` ({task})\n",
        f"**ارزیابی:** {metrics.get('verdict', '—')}\n",
    ]
    for k, v in metrics.items():
        if k == "verdict":
            continue
        if isinstance(v, float):
            lines.append(f"- {k}: **{v:.4f}**")
        else:
            lines.append(f"- {k}: **{v}**")
    if params and "grid_search_error" not in params:
        lines.append("\n### بهترین هایپرپارامترها")
        for k, v in params.items():
            lines.append(f"- {k}: `{v}`")
    if importances:
        lines.append("\n### مهم‌ترین ویژگی‌ها")
        for f in importances[:8]:
            lines.append(f"- {f['feature']}: {f['importance']:.4f}")
    v = metrics.get("verdict", "")
    if "ضعیف" in v:
        lines.append(
            "\n### پیشنهاد بعدی\n"
            "- Feature engineering (نسبت‌ها، لگاریتم، تعامل ویژگی‌ها)\n"
            "- حذف ویژگی‌های کم‌اهمیت\n"
            "- امتحان مدل دیگر (مثلاً XGBoost)\n"
            "- بررسی imbalance یا outliers"
        )
    elif "متوسط" in v:
        lines.append("\n### پیشنهاد بعدی\nمدل قابل‌قبول است؛ با tuning بیشتر یا ویژگی‌های جدید می‌توان بهتر کرد.")
    else:
        lines.append("\n### جمع‌بندی\nعملکرد مناسب است؛ می‌توانی مدل را برای استفاده ذخیره کنی.")

    # optional LLM polish
    try:
        from .ai_service import DEFAULT_MODEL, OLLAMA_HOST
        import ollama
        client = ollama.Client(host=OLLAMA_HOST) if OLLAMA_HOST else ollama
        resp = client.chat(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "تحلیل‌گر ML هستی. فارسی، کوتاه و کاربردی. اعداد را عوض نکن."},
                {"role": "user", "content": "این نتایج را تفسیر کن و بگو قدم بعدی چیست:\n" + "\n".join(lines)},
            ],
            options={"temperature": 0.3, "num_predict": 900},
        )
        msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", {})
        content = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
        if len(content) > 40:
            return content
    except Exception:
        pass
    return "\n".join(lines)



def improve_and_retrain(
    dataset_path: str,
    target_col: str,
    model_name: str = "RandomForest",
    task_type: Optional[str] = None,
    experiment_id: Optional[int] = None,
    drop_weak_features: bool = True,
    weak_fraction: float = 0.3,
    previous_importance: Optional[list] = None,
) -> dict:
    """حذف ویژگی‌های کم‌اهمیت از CSV تمیز و آموزش مجدد — جدول اصلی دست نمی‌خورد."""
    import pandas as pd

    path = Path(dataset_path)
    if not path.exists():
        return {"ok": False, "error": f"dataset نیست: {dataset_path}"}

    df = pd.read_csv(path)
    if target_col not in df.columns:
        return {"ok": False, "error": f"target نیست: {target_col}"}

    dropped = []
    if drop_weak_features and previous_importance:
        feats = [x.get("feature") for x in previous_importance if x.get("feature")]
        n_drop = max(1, int(len(feats) * float(weak_fraction)))
        # weakest are at the end of sorted-desc list from train
        weak = feats[-n_drop:] if feats else []
        for w in weak:
            if w in df.columns and w != target_col:
                df = df.drop(columns=[w])
                dropped.append(w)

    # always need at least 1 feature
    feat_cols = [c for c in df.columns if c != target_col]
    if not feat_cols:
        return {"ok": False, "error": "بعد از حذف ویژگی، ستونی نمانده"}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    new_path = ML_DIR / f"clean_improved_{ts}.csv"
    df.to_csv(new_path, index=False)

    result = train_model(
        dataset_path=str(new_path),
        target_col=target_col,
        model_name=model_name,
        task_type=task_type,
        grid_search=True,
        experiment_id=None,  # new experiment row
    )
    if not result.get("ok"):
        return result

    result["dropped_features"] = dropped
    result["dataset_path"] = str(new_path)
    result["note"] = "ویژگی‌های ضعیف حذف و مدل دوباره آموزش داده شد. جدول اصلی تغییر نکرد."

    # update notes on new experiment
    try:
        eid = result.get("experiment_id")
        if eid:
            store.execute(
                "UPDATE ml_experiments SET notes=?, table_name=(SELECT table_name FROM ml_experiments WHERE id=?) WHERE id=?",
                (
                    f"improved; dropped={dropped}",
                    int(experiment_id) if experiment_id else eid,
                    int(eid),
                ),
            )
    except Exception:
        pass

    return _json_safe(result)



def get_experiment(exp_id: int) -> dict:
    _ensure_ml_tables()
    r = store.fetchone("SELECT * FROM ml_experiments WHERE id=?", (int(exp_id),))
    if not r:
        return {"ok": False, "error": "آزمایش یافت نشد"}
    metrics = json.loads(r["metrics_json"] or "{}") if r["metrics_json"] else {}
    params = json.loads(r["params_json"] or "{}") if r["params_json"] else {}
    features = json.loads(r["feature_list"] or "[]") if r["feature_list"] else []
    preds = {}
    try:
        preds = json.loads(r["predictions_json"] or "{}") if r.get("predictions_json") else {}
    except Exception:
        preds = {}
    # feature importance not stored separately — optional load from joblib skipped
    return {
        "ok": True,
        "experiment": {
            "id": r["id"],
            "name": r["name"],
            "table_name": r["table_name"],
            "target_col": r["target_col"],
            "task_type": r["task_type"],
            "model_name": r["model_name"],
            "view_name": r["view_name"],
            "dataset_path": r["dataset_path"],
            "model_path": r["model_path"] if "model_path" in r.keys() else "",
            "metrics": metrics,
            "best_params": params,
            "features": features,
            "status": r["status"],
            "notes": r["notes"],
            "created_at": r["created_at"],
            "analysis": r["analysis_text"] if "analysis_text" in r.keys() else "",
            "predictions": preds,
            "n_features": len(features),
        },
    }



def predict_with_model(exp_id: int, records: list | None = None, dataset_path: str | None = None) -> dict:
    """Load saved joblib model and predict on new rows or a CSV dataset_path."""
    import math
    import numpy as np
    import pandas as pd
    from pathlib import Path as P

    _ensure_ml_tables()
    exp = get_experiment(int(exp_id))
    if not exp.get("ok"):
        return exp
    e = exp["experiment"]
    model_path = e.get("model_path") or ""
    if not model_path or not P(model_path).exists():
        return {"ok": False, "error": "فایل مدل پیدا نشد — یک‌بار دیگر مدل را Train و Finalize کن"}

    try:
        import joblib
        bundle = joblib.load(model_path)
    except Exception as err:
        return {"ok": False, "error": f"بارگذاری مدل: {err}"}

    model = bundle.get("model")
    features = list(bundle.get("features") or e.get("features") or [])
    cat_maps = bundle.get("cat_maps") or {}
    label_classes = bundle.get("label_classes")
    task = bundle.get("task") or e.get("task_type") or "regression"
    target = bundle.get("target") or e.get("target_col")

    if dataset_path:
        try:
            df = pd.read_csv(dataset_path)
        except Exception as err:
            return {"ok": False, "error": f"خواندن CSV: {err}"}
    elif records:
        df = pd.DataFrame(records)
    else:
        return {
            "ok": False,
            "error": "records یا dataset_path لازم است",
            "features_required": features,
            "task": task,
            "target": target,
            "model_path": model_path,
            "load_snippet": (
                "import joblib\n"
                f"bundle = joblib.load(r'{model_path}')\n"
                "model = bundle['model']\n"
                "features = bundle['features']\n"
                "# X = df[features]  then model.predict(X)\n"
            ),
        }

    missing = [f for f in features if f not in df.columns]
    if missing:
        return {
            "ok": False,
            "error": f"ستون‌های لازم کم است: {missing}",
            "features_required": features,
            "got_columns": list(df.columns),
        }

    X = df[features].copy()
    for col, mapping in (cat_maps or {}).items():
        if col in X.columns:
            X[col] = X[col].map(lambda v, m=mapping: m.get(v, m.get(str(v), 0))).astype(float)
    for col in X.columns:
        if X[col].dtype == object:
            X[col] = pd.Categorical(X[col]).codes.astype(float)
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0)

    try:
        pred = model.predict(X)
    except Exception as err:
        return {"ok": False, "error": f"predict failed: {err}"}

    pred_list = []
    for p in pred:
        if label_classes is not None:
            try:
                idx = int(p)
                pred_list.append(str(label_classes[idx]) if 0 <= idx < len(label_classes) else str(p))
                continue
            except Exception:
                pass
        try:
            fv = float(p)
            if math.isnan(fv) or math.isinf(fv):
                pred_list.append(None)
            else:
                pred_list.append(fv)
        except Exception:
            pred_list.append(str(p))

    out_rows = df.copy()
    out_rows["prediction"] = pred_list

    metrics = {}
    if target and target in df.columns:
        try:
            y_true = df[target]
            if task == "classification":
                from sklearn.metrics import accuracy_score, f1_score
                yt = y_true.astype(str)
                yp = pd.Series(pred_list).astype(str)
                metrics = {
                    "accuracy": float(accuracy_score(yt, yp)),
                    "f1_weighted": float(f1_score(yt, yp, average="weighted", zero_division=0)),
                }
            else:
                from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
                yt = pd.to_numeric(y_true, errors="coerce")
                yp = pd.to_numeric(pd.Series(pred_list), errors="coerce")
                mask = yt.notna() & yp.notna()
                if mask.sum() > 0:
                    metrics = {
                        "r2": float(r2_score(yt[mask], yp[mask])),
                        "mae": float(mean_absolute_error(yt[mask], yp[mask])),
                        "rmse": float(mean_squared_error(yt[mask], yp[mask]) ** 0.5),
                    }
        except Exception:
            metrics = {}

    sample = out_rows.head(100).to_dict(orient="records")
    for r in sample:
        for k, v in list(r.items()):
            if hasattr(v, "item"):
                try:
                    r[k] = v.item()
                except Exception:
                    r[k] = str(v)
            elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                r[k] = None

    return _json_safe({
        "ok": True,
        "experiment_id": int(exp_id),
        "model_path": model_path,
        "task": task,
        "target": target,
        "features": features,
        "n_rows": int(len(pred_list)),
        "predictions": pred_list[:500],
        "rows": sample,
        "metrics": metrics,
        "load_snippet": (
            "import joblib\n"
            f"bundle = joblib.load(r'{model_path}')\n"
            "model = bundle['model']\n"
            "features = bundle['features']\n"
            "cat_maps = bundle.get('cat_maps') or {}\n"
            "# prepare X with same features order, then:\n"
            "# preds = model.predict(X)\n"
        ),
    })


def list_experiments(limit: int = 30) -> dict:
    _ensure_ml_tables()
    rows = store.fetchall(
        "SELECT * FROM ml_experiments ORDER BY id DESC LIMIT ?",
        (int(limit),),
    )
    out = []
    for r in rows:
        keys = r.keys() if hasattr(r, "keys") else []
        out.append({
            "id": r["id"],
            "name": r["name"],
            "table_name": r["table_name"],
            "target_col": r["target_col"],
            "task_type": r["task_type"],
            "model_name": r["model_name"],
            "view_name": r["view_name"],
            "dataset_path": r["dataset_path"],
            "model_path": r["model_path"] if "model_path" in keys else "",
            "metrics": json.loads(r["metrics_json"] or "{}") if r["metrics_json"] else {},
            "status": r["status"],
            "notes": r["notes"],
            "created_at": r["created_at"],
        })
    return {"experiments": out}


def ml_chat(message: str, context: Optional[dict] = None) -> dict:
    """چت کمکی مخصوص تب ML — context از ویزارد."""
    ctx = context or {}
    try:
        from .ai_service import DEFAULT_MODEL, OLLAMA_HOST
        import ollama
        client = ollama.Client(host=OLLAMA_HOST) if OLLAMA_HOST else ollama
        resp = client.chat(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "تو دستیار ML Studio در Data Observatory هستی. "
                        "کاربر در حال ساخت مدل روی جداول Postgres است. "
                        "راهنمایی عملی بده: target، پیش‌پردازش، مدل، feature engineering. "
                        "فارسی بنویس. عدد جعلی نساز. جدول اصلی را تغییر نده — فقط VIEW/dataset تمیز."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Context:\n{json.dumps(ctx, ensure_ascii=False, default=str)[:8000]}\n\nسوال:\n{message}",
                },
            ],
            options={"temperature": 0.3, "num_predict": 1200},
        )
        msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", {})
        content = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
        return {"ok": True, "answer": content}
    except Exception as e:
        return {
            "ok": True,
            "answer": (
                "مدل زبانی در دسترس نیست، اما مسیر پیشنهادی:\n"
                "1) جدول را Analyze کن\n"
                "2) target را از پیشنهادها انتخاب کن\n"
                "3) Prepare (VIEW/CSV تمیز)\n"
                "4) مدل + GridSearch\n"
                f"\n_(خطا: {e})_"
            ),
        }
