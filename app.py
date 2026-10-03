"""
Data Observatory — Enterprise Data Platform
uvicorn app:app --host 0.0.0.0 --port 8700 --reload
"""
from __future__ import annotations

from typing import Any, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path

from core import store, services
from core.config import STATIC_DIR, APP_NAME

store.ensure_db(seed=False)  # no demo data by default

@asynccontextmanager
async def lifespan(app: FastAPI):
    from core import store
    store.init_schema()
    try:
        store._migrate()
    except Exception:
        pass
    # Demo seed disabled — catalog starts empty; use Auto Discovery + metadata packs
    try:
        from core.metadata_loader import apply_all_packs
        apply_all_packs()  # apply packs to any already-registered tables
    except Exception:
        pass
    yield

app = FastAPI(lifespan=lifespan, title=APP_NAME, version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SparkIn(BaseModel):
    database: str = "PostgreSQL"
    table: str = "MeterData"
    group_by: str = "companyCode"
    metric: str = "AVG(consumption)"
    days: int = 30


class SqlIn(BaseModel):
    sql: str = Field(..., min_length=1)
    limit: int = 200
    engine: str = "postgres"


class DiscoverIn(BaseModel):
    host: str = ""
    port: int = 5432
    database: str = ""
    db_type: str = "PostgreSQL"
    user: str = ""
    password: str = ""
    schema_filter: Optional[str] = None


@app.get("/api/overview")
def api_overview():
    return services.overview()


@app.get("/api/catalog")
def api_catalog():
    return services.catalog_tree()


@app.get("/api/tables/{table_id}")
def api_table(table_id: int):
    d = services.table_detail(table_id)
    if not d:
        raise HTTPException(404, "Table not found")
    return d


@app.get("/api/freshness")
def api_freshness():
    return services.freshness_list()


@app.get("/api/freshness/dashboard")
def api_freshness_dashboard():
    return services.freshness_dashboard()


@app.get("/api/tables/{table_id}/ai-metadata")
def api_ai_metadata(table_id: int):
    d = services.ai_table_metadata(table_id)
    if not d:
        raise HTTPException(404, "Table not found")
    return d


@app.get("/api/metadata/ai-export")
def api_ai_export(limit: int = 500):
    return services.ai_catalog_export(limit)


@app.get("/api/schema-changes")
def api_schema_changes(limit: int = 50):
    return services.schema_changes(limit)


@app.get("/api/quality")
def api_quality():
    return services.quality_summary()


@app.get("/api/profiler/{table_id}")
def api_profiler(table_id: int):
    d = services.profiler(table_id)
    if not d:
        raise HTTPException(404, "Table not found")
    return d


@app.get("/api/growth")
def api_growth(table_id: Optional[int] = None):
    return services.growth_series(table_id)


@app.get("/api/alerts")
def api_alerts():
    return services.alerts_list()


@app.get("/api/health")
def api_health():
    return services.health_board()


@app.post("/api/scan")
def api_scan():
    return services.run_scan()


@app.post("/api/spark")
def api_spark(body: SparkIn):
    return services.spark_query_demo(body.model_dump())


@app.post("/api/sql")
def api_sql(body: SqlIn):
    return services.sql_explore(body.sql, limit=body.limit, engine=body.engine)


@app.get("/api/sql/templates")
def api_sql_templates():
    return services.sql_templates()



@app.get("/api/sql/live-tables")
def api_sql_live_tables():
    return services.sql_list_live_tables()


@app.get("/api/sql/table/{table_name}/data")
def api_sql_table_data(table_name: str, schema: str = "public", offset: int = 0, limit: int = 100):
    return services.sql_table_data(table_name, schema=schema, offset=offset, limit=limit)


@app.get("/api/sql/table/{table_name}/info")
def api_sql_table_info(table_name: str, schema: str = "public"):
    return services.sql_table_info(table_name, schema=schema)


@app.get("/api/sql/history")
def api_sql_history(limit: int = 30):
    return services.sql_history(limit)


@app.get("/api/bi/settings")
def api_bi_settings():
    return services.bi_settings()


@app.post("/api/bi/query")
def api_bi_query(body: dict = Body(...)):
    return services.bi_query(body or {})


@app.post("/api/bi/export-pdf")
def api_bi_export_pdf(body: dict = Body(...)):
    return services.bi_export_pdf(body or {})


@app.get("/api/bi/dashboards")
def api_bi_list_dashboards():
    return services.bi_list_dashboards()


@app.get("/api/bi/dashboards/{dash_id}")
def api_bi_get_dashboard(dash_id: int):
    return services.bi_get_dashboard(dash_id)


@app.post("/api/bi/dashboards")
def api_bi_save_dashboard(body: dict = Body(...)):
    raw_id = body.get("id")
    dash_id = int(raw_id) if raw_id not in (None, "", "null") else None
    return services.bi_save_dashboard(
        name=body.get("name") or "Dashboard",
        payload=body.get("payload") or {},
        dash_id=dash_id,
    )


@app.delete("/api/bi/dashboards/{dash_id}")
def api_bi_delete_dashboard(dash_id: int):
    return services.bi_delete_dashboard(dash_id)


@app.get("/api/bi/exports/{filename}")
def api_bi_download_export(filename: str):
    from fastapi.responses import FileResponse
    from pathlib import Path
    safe = Path(filename).name
    if not safe.endswith(".pdf"):
        return {"ok": False, "error": "invalid file"}
    path = Path(__file__).resolve().parent / "data" / "bi_exports" / safe
    if not path.exists():
        return {"ok": False, "error": "not found"}
    return FileResponse(path, media_type="application/pdf", filename=safe)



@app.put("/api/tables/{table_id}/sla")
def api_table_sla(table_id: int, body: dict = Body(...)):
    return services.update_table_sla(
        table_id,
        float(body.get("expected_interval_hours", 24)),
        float(body.get("sla_hours", 26)),
    )


@app.put("/api/tables/{table_id}/metadata")
def api_table_meta(table_id: int, body: dict = Body(...)):
    return services.update_table_metadata(
        table_id,
        description=body.get("description", ""),
        owner=body.get("owner", ""),
        tags=body.get("tags", ""),
    )


@app.put("/api/columns/{column_id}/metadata")
def api_col_meta(column_id: int, body: dict = Body(...)):
    # Rich AI metadata: pass through all supported fields
    return services.update_column_metadata(column_id, **(body or {}))


@app.post("/api/tables/{table_id}/auto-metadata")
def api_auto_meta(table_id: int):
    return services.auto_generate_metadata(table_id)


@app.get("/api/quality/by-type")
def api_quality_by_type():
    try:
        return services.quality_by_type()
    except Exception as e:
        return {"types": [], "by_type": {}, "error": str(e)}


@app.get("/api/metadata/tables")
def api_meta_tables():
    """List tables for metadata editor."""
    try:
        store._migrate()
    except Exception:
        pass
    try:
        rows = store.fetchall(
            """SELECT t.id, t.table_name,
                      COALESCE(t.description,'') AS description,
                      COALESCE(t.owner,'') AS owner,
                      COALESCE(t.tags,'') AS tags,
                      t.expected_interval_hours, t.sla_hours, t.status, t.last_update,
                      s.schema_name, d.name AS db_name
               FROM tables t
               JOIN schemas s ON s.id=t.schema_id
               JOIN databases d ON d.id=s.database_id
               ORDER BY d.name, s.schema_name, t.table_name"""
        )
        return rows
    except Exception as e:
        raise HTTPException(500, f"metadata query failed: {e}")


@app.post("/api/catalog/clear")
def api_clear_catalog():
    return services.clear_demo_data()


@app.post("/api/discover")

def api_discover(body: DiscoverIn):
    return services.discover_postgres(body.host, body.port, body.database, body.user, body.password, body.schema_filter)




@app.get("/api/metadata/packs")
def api_metadata_packs():
    from core.metadata_loader import list_metadata_packs
    return list_metadata_packs()


@app.post("/api/metadata/apply")
def api_metadata_apply(body: dict = Body(default={})):
    """Apply metadata pack(s). body: {file?: str, all?: bool}"""
    from core.metadata_loader import apply_all_packs, apply_pack_file
    if body.get("all") or not body.get("file"):
        return apply_all_packs()
    return apply_pack_file(str(body.get("file")))


class AiChatIn(BaseModel):
    message: str = Field(..., min_length=1)
    history: Optional[list] = None
    model: Optional[str] = None


@app.get("/api/ai/status")
def api_ai_status():
    from core.ai_service import get_llm
    return get_llm().status()


@app.post("/api/ai/chat")
def api_ai_chat(body: AiChatIn):
    from core.ai_service import get_llm
    llm = get_llm(body.model)
    return llm.chat(body.message, history=body.history or [])



class MlProfileIn(BaseModel):
    table_name: str
    table_id: Optional[int] = None
    sample_limit: int = 3000


class MlPrepareIn(BaseModel):
    table_name: str
    target_col: str
    feature_cols: Optional[list] = None
    drop_cols: Optional[list] = None
    create_sql_view: bool = True
    sample_limit: int = 10000


class MlTrainIn(BaseModel):
    dataset_path: str
    target_col: str
    model_name: str = "RandomForest"
    task_type: Optional[str] = None
    test_size: float = 0.2
    grid_search: bool = True
    experiment_id: Optional[int] = None


class MlChatIn(BaseModel):
    message: str = Field(..., min_length=1)
    context: Optional[dict] = None


@app.get("/api/ml/tables")
def api_ml_tables():
    from core import ml_service
    return ml_service.list_catalog_tables()


@app.post("/api/ml/analyze")
def api_ml_analyze(body: MlProfileIn):
    from core import ml_service
    return ml_service.ai_advise_table(body.table_name, table_id=body.table_id)


@app.post("/api/ml/prepare")
def api_ml_prepare(body: MlPrepareIn):
    from core import ml_service
    return ml_service.build_clean_dataset(
        table_name=body.table_name,
        target_col=body.target_col,
        feature_cols=body.feature_cols,
        drop_cols=body.drop_cols,
        create_sql_view=body.create_sql_view,
        sample_limit=body.sample_limit,
    )


@app.post("/api/ml/train")
def api_ml_train(body: MlTrainIn):
    from core import ml_service
    try:
        return ml_service.train_model(
            dataset_path=body.dataset_path,
            target_col=body.target_col,
            model_name=body.model_name,
            task_type=body.task_type,
            test_size=body.test_size,
            grid_search=body.grid_search,
            experiment_id=body.experiment_id,
        )
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()[-1500:]}


@app.get("/api/ml/experiments")
def api_ml_experiments(limit: int = 30):
    from core import ml_service
    return ml_service.list_experiments(limit=limit)



class MlImproveIn(BaseModel):
    dataset_path: str
    target_col: str
    model_name: str = "RandomForest"
    task_type: Optional[str] = None
    experiment_id: Optional[int] = None
    drop_weak_features: bool = True
    weak_fraction: float = 0.3
    previous_importance: Optional[list] = None


@app.post("/api/ml/improve")
def api_ml_improve(body: MlImproveIn):
    from core import ml_service
    try:
        return ml_service.improve_and_retrain(
            dataset_path=body.dataset_path,
            target_col=body.target_col,
            model_name=body.model_name,
            task_type=body.task_type,
            experiment_id=body.experiment_id,
            drop_weak_features=body.drop_weak_features,
            weak_fraction=body.weak_fraction,
            previous_importance=body.previous_importance,
        )
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()[-1500:]}



@app.get("/api/ml/experiments/{exp_id}")
def api_ml_experiment(exp_id: int):
    from core import ml_service
    return ml_service.get_experiment(exp_id)


class MlPredictIn(BaseModel):
    experiment_id: int
    records: Optional[list] = None
    dataset_path: Optional[str] = None


@app.post("/api/ml/predict")
def api_ml_predict(body: MlPredictIn):
    from core import ml_service
    try:
        return ml_service.predict_with_model(
            exp_id=body.experiment_id,
            records=body.records,
            dataset_path=body.dataset_path,
        )
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()[-1200:]}


class NbSessionIn(BaseModel):
    table_name: Optional[str] = None
    sample_limit: int = 10000


class NbExecIn(BaseModel):
    session_id: str
    code: str
    cell_id: Optional[str] = None


@app.post("/api/ml/notebook/session")
def api_nb_session(body: NbSessionIn):
    from core import ml_notebook
    return ml_notebook.create_session(table_name=body.table_name, sample_limit=body.sample_limit)


@app.post("/api/ml/notebook/exec")
def api_nb_exec(body: NbExecIn):
    from core import ml_notebook
    return ml_notebook.execute_cell(body.session_id, body.code, cell_id=body.cell_id)


@app.post("/api/ml/notebook/reset")
def api_nb_reset(body: dict = Body(...)):
    from core import ml_notebook
    return ml_notebook.reset_session(body.get("session_id") or "")


@app.get("/api/ml/notebook/sessions")
def api_nb_sessions():
    from core import ml_notebook
    return ml_notebook.list_sessions()


@app.get("/api/ml/notebooks")
def api_ml_list_notebooks():
    return services.nb_list_notebooks()


@app.get("/api/ml/notebooks/{nb_id}")
def api_ml_get_notebook(nb_id: int):
    return services.nb_get_notebook(nb_id)


@app.post("/api/ml/notebooks")
def api_ml_save_notebook(body: dict = Body(...)):
    raw_id = body.get("id")
    nb_id = int(raw_id) if raw_id not in (None, "", "null") else None
    return services.nb_save_notebook(
        name=body.get("name") or "Notebook",
        cells=body.get("cells") or [],
        table_name=body.get("table_name") or "",
        nb_id=nb_id,
    )


@app.delete("/api/ml/notebooks/{nb_id}")
def api_ml_delete_notebook(nb_id: int):
    return services.nb_delete_notebook(nb_id)


@app.post("/api/ml/chat")
def api_ml_chat(body: MlChatIn):
    from core import ml_service
    return ml_service.ml_chat(body.message, context=body.context)




# ---------- Pipeline / Warehouse Studio ----------
@app.get("/api/pipeline/list")
def api_pipeline_list():
    from core import pipeline_service
    return pipeline_service.list_pipelines()


@app.get("/api/pipeline/lake-tables")
def api_pipeline_lake():
    from core import pipeline_service
    return pipeline_service.lake_tables()


@app.get("/api/pipeline/columns")
def api_pipeline_columns(schema: str = "public", table: str = ""):
    from core import pipeline_service
    return pipeline_service.table_columns(schema, table)


@app.get("/api/pipeline/{pid}")
def api_pipeline_get(pid: int):
    from core import pipeline_service
    return pipeline_service.get_pipeline(pid)


@app.get("/api/pipeline/{pid}/info")
def api_pipeline_info(pid: int):
    from core import pipeline_service
    return pipeline_service.pipeline_info(pid)


@app.post("/api/pipeline/save")
def api_pipeline_save(body: dict = Body(...)):
    from core import pipeline_service
    return pipeline_service.save_pipeline(body or {})


@app.post("/api/pipeline/warehouse")
def api_pipeline_warehouse(body: dict = Body(...)):
    from core import pipeline_service
    return pipeline_service.create_warehouse(body or {})


@app.post("/api/pipeline/compile")
def api_pipeline_compile(body: dict = Body(...)):
    from core import pipeline_service
    return pipeline_service.compile_sql(body or {})


@app.delete("/api/pipeline/{pid}")
def api_pipeline_delete(pid: int):
    from core import pipeline_service
    return pipeline_service.delete_pipeline(pid)


@app.get("/api/pipeline/{pid}/properties")
def api_pipeline_properties(pid: int):
    from core import pipeline_service
    return pipeline_service.warehouse_properties(pid)


@app.post("/api/pipeline/{pid}/materialize")
def api_pipeline_materialize(pid: int):
    from core import pipeline_service
    return pipeline_service.materialize_pipeline(pid)


@app.post("/api/pipeline/{pid}/preview")
def api_pipeline_preview(pid: int, body: dict = Body(...)):
    from core import pipeline_service
    return pipeline_service.preview_node(
        pid,
        node_id=body.get("node_id") or "",
        limit=int(body.get("limit") or 50),
    )


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8701, reload=True)
