"""
ML PRO Notebook kernel — Jupyter-like cell execution with persistent namespace.
"""
from __future__ import annotations

import io
import json
import traceback
import uuid
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .config import DATA_DIR
from .ml_service import _fetch_frame, ML_DIR

NB_DIR = DATA_DIR / "ml" / "notebooks"
NB_DIR.mkdir(parents=True, exist_ok=True)

# in-memory kernels: session_id -> {globals, created, table, csv_path}
_SESSIONS: Dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _bootstrap_globals(csv_path: Optional[str] = None, table_name: Optional[str] = None) -> dict:
    import math
    import numpy as np

    g: Dict[str, Any] = {"__name__": "__main__"}
    try:
        import pandas as pd
        g["pd"] = pd
        g["pandas"] = pd
    except ImportError:
        pd = None
    g["np"] = np
    g["numpy"] = np
    g["math"] = math

    try:
        import sklearn
        g["sklearn"] = sklearn
        from sklearn import model_selection, metrics, preprocessing, ensemble, linear_model
        g["model_selection"] = model_selection
        g["metrics"] = metrics
        g["preprocessing"] = preprocessing
        g["ensemble"] = ensemble
        g["linear_model"] = linear_model
    except ImportError:
        pass

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import cycler
        # attractive dark theme for notebook chart outputs only
        plt.rcParams.update({
            "figure.facecolor": "#0b1220",
            "axes.facecolor": "#121a2b",
            "axes.edgecolor": "#334155",
            "axes.labelcolor": "#e2e8f0",
            "axes.titlecolor": "#f1f5f9",
            "xtick.color": "#94a3b8",
            "ytick.color": "#94a3b8",
            "text.color": "#e2e8f0",
            "grid.color": "#1e293b",
            "grid.linestyle": "--",
            "grid.alpha": 0.7,
            "legend.facecolor": "#151d30",
            "legend.edgecolor": "#334155",
            "axes.prop_cycle": cycler(color=[
                "#8b5cf6", "#06b6d4", "#22c55e", "#f59e0b",
                "#ef4444", "#3b82f6", "#ec4899", "#14b8a6",
                "#a855f7", "#f97316",
            ]),
            "lines.linewidth": 2.4,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "figure.dpi": 120,
        })
        g["plt"] = plt
        g["matplotlib"] = matplotlib
    except ImportError:
        pass
    try:
        import plotly.io as pio
        import plotly.graph_objects as go
        import plotly.express as px
        pio.templates.default = "plotly_dark"
        g["pio"] = pio
        g["go"] = go
        g["px"] = px
    except ImportError:
        pass

    try:
        import joblib
        g["joblib"] = joblib
    except ImportError:
        pass

    # data helpers
    g["DATA_DIR"] = str(DATA_DIR)
    g["ML_DIR"] = str(ML_DIR)
    if csv_path and pd is not None:
        try:
            g["df"] = pd.read_csv(csv_path)
            g["CSV_PATH"] = csv_path
        except Exception as e:
            g["df"] = None
            g["CSV_PATH"] = csv_path
            g["_csv_error"] = str(e)
    else:
        g["df"] = None
        g["CSV_PATH"] = None
    g["TABLE_NAME"] = table_name
    return g


def create_session(table_name: Optional[str] = None, sample_limit: int = 10000) -> dict:
    """Create notebook session; optionally materialize table to CSV as df."""
    session_id = uuid.uuid4().hex[:12]
    csv_path = None
    rows = 0
    cols = 0
    note = ""

    if table_name:
        df, err = _fetch_frame(table_name, limit=sample_limit)
        if err:
            return {"ok": False, "error": err}
        import pandas as pd
        if df is None:
            df = pd.DataFrame()
        path = ML_DIR / f"nb_{table_name}_{session_id}.csv"
        df.to_csv(path, index=False)
        csv_path = str(path)
        rows, cols = int(df.shape[0]), int(df.shape[1])
        note = f"df از جدول `{table_name}` بارگذاری شد ({rows}×{cols}). مسیر: CSV_PATH"
    else:
        note = "بدون جدول — خودت pd.read_csv یا داده بساز."

    g = _bootstrap_globals(csv_path=csv_path, table_name=table_name)
    _SESSIONS[session_id] = {
        "globals": g,
        "created": _now(),
        "table_name": table_name,
        "csv_path": csv_path,
        "cells": [],
    }
    return {
        "ok": True,
        "session_id": session_id,
        "table_name": table_name,
        "csv_path": csv_path,
        "rows": rows,
        "cols": cols,
        "note": note,
        "hints": [
            "df — DataFrame آماده‌شده از جدول",
            "pd / np / plt / sklearn در دسترس است",
            "CSV_PATH — مسیر فایل CSV",
            "آخرین عبارت هر سلول نمایش داده می‌شود",
        ],
    }


def get_session(session_id: str) -> Optional[dict]:
    return _SESSIONS.get(session_id)


def reset_session(session_id: str) -> dict:
    s = _SESSIONS.get(session_id)
    if not s:
        return {"ok": False, "error": "session یافت نشد"}
    g = _bootstrap_globals(csv_path=s.get("csv_path"), table_name=s.get("table_name"))
    s["globals"] = g
    s["cells"] = []
    return {"ok": True, "session_id": session_id, "note": "kernel ریست شد"}


def _format_result(val: Any) -> dict:
    """Serialize execution result for UI."""
    if val is None:
        return {"type": "none", "text": ""}
    try:
        import pandas as pd
        if isinstance(val, pd.DataFrame):
            return {
                "type": "dataframe",
                "text": val.head(30).to_string(),
                "html": val.head(30).to_html(classes="nb-df", border=0),
                "shape": list(val.shape),
            }
        if isinstance(val, pd.Series):
            return {"type": "series", "text": val.head(40).to_string()}
    except Exception:
        pass
    try:
        import numpy as np
        if isinstance(val, np.ndarray):
            return {"type": "ndarray", "text": np.array2string(val, threshold=100)}
    except Exception:
        pass
    # matplotlib figure
    try:
        import matplotlib.pyplot as plt
        from matplotlib.figure import Figure
        fig = None
        if isinstance(val, Figure):
            fig = val
        elif hasattr(val, "figure"):
            fig = val.figure
        if fig is None and plt.get_fignums():
            fig = plt.gcf()
        if fig is not None and plt.get_fignums():
            import base64
            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", dpi=140, facecolor="#0b1220", edgecolor="none")
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode("ascii")
            plt.close("all")
            return {"type": "image", "text": "[plot]", "image_base64": b64}
    except Exception:
        pass
    text = str(val)
    if len(text) > 8000:
        text = text[:8000] + "\n… truncated"
    return {"type": "text", "text": text}


def execute_cell(session_id: str, code: str, cell_id: Optional[str] = None) -> dict:
    s = _SESSIONS.get(session_id)
    if not s:
        return {"ok": False, "error": "session منقضی یا نامعتبر — یک session جدید بساز"}

    code = (code or "").strip()
    if not code:
        return {"ok": False, "error": "کد خالی است"}

    # light safety: block obvious destructive OS ops
    banned = ["os.system", "subprocess", "shutil.rmtree", "__import__('os')", "open('/", "Path('/')"]
    low = code.replace(" ", "")
    for b in banned:
        if b in code or b in low:
            return {"ok": False, "error": f"کد مسدود شد: {b}"}

    g = s["globals"]
    stdout = io.StringIO()
    stderr = io.StringIO()
    result_val = None
    error = None

    # evaluate last expression if possible (ipython-like)
    import ast
    try:
        tree = ast.parse(code)
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            *body, last = tree.body
            mod = ast.Module(body=body, type_ignores=[])
            ast.fix_missing_locations(mod)
            with redirect_stdout(stdout), redirect_stderr(stderr):
                if body:
                    exec(compile(mod, "<cell>", "exec"), g, g)
                result_val = eval(compile(ast.Expression(last.value), "<cell>", "eval"), g, g)
        else:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exec(compile(code, "<cell>", "exec"), g, g)
            # capture matplotlib if plotted without return
            try:
                import matplotlib.pyplot as plt
                if plt.get_fignums():
                    result_val = plt.gcf()
            except Exception:
                pass
    except Exception:
        error = traceback.format_exc()

    out = stdout.getvalue()
    err = stderr.getvalue()
    payload = {
        "ok": error is None,
        "session_id": session_id,
        "cell_id": cell_id,
        "stdout": out,
        "stderr": err,
        "error": error,
        "result": _format_result(result_val) if error is None else None,
    }
    s["cells"].append({"code": code, "ok": payload["ok"], "at": _now()})
    # auto-save notebook snapshot
    try:
        snap = NB_DIR / f"{session_id}.json"
        snap.write_text(json.dumps({
            "session_id": session_id,
            "table": s.get("table_name"),
            "csv_path": s.get("csv_path"),
            "cells": s["cells"][-50:],
            "updated": _now(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return payload


def list_sessions() -> dict:
    return {
        "sessions": [
            {
                "session_id": sid,
                "table_name": s.get("table_name"),
                "csv_path": s.get("csv_path"),
                "created": s.get("created"),
                "n_cells": len(s.get("cells") or []),
            }
            for sid, s in _SESSIONS.items()
        ]
    }
