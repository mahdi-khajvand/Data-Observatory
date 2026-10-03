"""
بارگذاری بسته‌های متادیتا از پوشه data/metadata/*.json
و اعمال روی جداول هم‌نام در کاتالوگ Observatory.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from . import store
from .config import DATA_DIR, BASE_DIR

log = logging.getLogger("metadata_loader")

# چند مسیر محتمل برای پیدا کردن pack (نصب‌های مختلف)
def _candidate_dirs() -> list[Path]:
    dirs = [
        DATA_DIR / "metadata",
        BASE_DIR / "data" / "metadata",
        Path(__file__).resolve().parent.parent / "data" / "metadata",
        Path.cwd() / "data" / "metadata",
        Path.cwd() / "metadata",
    ]
    # unique preserve order
    seen = set()
    out = []
    for d in dirs:
        try:
            key = str(d.resolve())
        except Exception:
            key = str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def metadata_dir() -> Path:
    for d in _candidate_dirs():
        if d.is_dir() and any(d.glob("*.json")):
            return d
    # default create
    d = DATA_DIR / "metadata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_metadata_packs() -> list[dict]:
    packs = []
    found_any = False
    for d in _candidate_dirs():
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.json")):
            found_any = True
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                packs.append({
                    "file": p.name,
                    "path": str(p.resolve()),
                    "name": data.get("name") or p.stem,
                    "description": data.get("description") or "",
                    "version": data.get("version") or "",
                    "table_count": len(data.get("tables") or []),
                    "tables": [t.get("table_name") for t in (data.get("tables") or [])],
                })
            except Exception as e:
                packs.append({"file": p.name, "path": str(p), "error": str(e)})
        if found_any:
            break
    return packs


def _load_pack_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_schema() -> None:
    """مطمئن شو فیلدهای غنی روی columns/tables وجود دارند."""
    try:
        store.init_schema()
    except Exception:
        pass
    try:
        store._migrate()
    except Exception as e:
        log.warning("migrate failed: %s", e)


def apply_pack_dict(data: dict, only_table: Optional[str] = None) -> dict[str, Any]:
    """اعمال یک بسته متادیتا روی جداول موجود در store."""
    _ensure_schema()
    tables_meta = data.get("tables") or []
    applied = []
    skipped = []
    errors = []

    catalog_names = [
        r["table_name"] for r in store.fetchall("SELECT table_name FROM tables")
    ]

    for tmeta in tables_meta:
        tname = (tmeta.get("table_name") or "").strip()
        if not tname:
            continue
        if only_table and only_table.lower() != tname.lower():
            continue

        # match case-insensitive; also try without schema prefix
        rows = store.fetchall(
            "SELECT id, table_name FROM tables WHERE lower(table_name) = lower(?)",
            (tname,),
        )
        if not rows:
            # try stripped match (e.g. public.income_statements stored weirdly)
            rows = store.fetchall(
                "SELECT id, table_name FROM tables WHERE lower(table_name) LIKE lower(?)",
                (f"%{tname}",),
            )
        if not rows:
            skipped.append({
                "table": tname,
                "reason": "not_in_catalog",
                "catalog_tables": catalog_names[:30],
            })
            continue

        for row in rows:
            tid = row["id"]
            try:
                store.execute(
                    "UPDATE tables SET description=?, owner=?, tags=? WHERE id=?",
                    (
                        tmeta.get("description") or "",
                        tmeta.get("owner") or "",
                        tmeta.get("tags") or "",
                        tid,
                    ),
                )
            except Exception as e:
                errors.append({"table": tname, "error": f"table update: {e}"})
                continue

            cols_applied = 0
            cols_missing = []
            for cmeta in tmeta.get("columns") or []:
                cname = (cmeta.get("column_name") or "").strip()
                if not cname:
                    continue
                col = store.fetchone(
                    "SELECT id FROM columns WHERE table_id=? AND lower(column_name)=lower(?)",
                    (tid, cname),
                )
                if not col:
                    cols_missing.append(cname)
                    continue
                try:
                    store.execute(
                        """UPDATE columns SET
                            description=?,
                            business_name=?,
                            semantic_type=?,
                            unit=?,
                            synonyms=?,
                            business_definition=?,
                            calculation_formula=?,
                            allowed_values=?,
                            example_value=CASE WHEN ? != '' THEN ? ELSE example_value END,
                            is_pk=?,
                            is_pii=?,
                            is_measure=?,
                            is_dimension=?,
                            ai_notes=?
                           WHERE id=?""",
                        (
                            cmeta.get("description") or "",
                            cmeta.get("business_name") or "",
                            cmeta.get("semantic_type") or "",
                            cmeta.get("unit") or "",
                            cmeta.get("synonyms") or "",
                            cmeta.get("business_definition") or "",
                            cmeta.get("calculation_formula") or "",
                            cmeta.get("allowed_values") or "",
                            str(cmeta.get("example_value") or ""),
                            str(cmeta.get("example_value") or ""),
                            int(cmeta.get("is_pk") or 0),
                            int(cmeta.get("is_pii") or 0),
                            int(cmeta.get("is_measure") or 0),
                            int(cmeta.get("is_dimension") or 0),
                            cmeta.get("ai_notes") or "",
                            col["id"],
                        ),
                    )
                    cols_applied += 1
                except Exception as e:
                    # fallback: maybe some columns missing — try minimal set
                    try:
                        store.execute(
                            """UPDATE columns SET description=?, business_name=?, semantic_type=?,
                               is_measure=?, is_dimension=?, is_pk=?, is_pii=? WHERE id=?""",
                            (
                                cmeta.get("description") or "",
                                cmeta.get("business_name") or "",
                                cmeta.get("semantic_type") or "",
                                int(cmeta.get("is_measure") or 0),
                                int(cmeta.get("is_dimension") or 0),
                                int(cmeta.get("is_pk") or 0),
                                int(cmeta.get("is_pii") or 0),
                                col["id"],
                            ),
                        )
                        cols_applied += 1
                    except Exception as e2:
                        errors.append({"table": tname, "column": cname, "error": str(e2)})

            applied.append({
                "table_id": tid,
                "table": row["table_name"],
                "columns_updated": cols_applied,
                "columns_missing_in_db": cols_missing,
            })

    return {
        "ok": True,
        "pack": data.get("name"),
        "version": data.get("version"),
        "applied": applied,
        "skipped": skipped,
        "errors": errors,
        "catalog_table_count": len(catalog_names),
    }


def apply_pack_file(filename: str, only_table: Optional[str] = None) -> dict:
    path = None
    # search all candidate dirs
    for d in _candidate_dirs():
        cand = d / filename
        if cand.exists():
            path = cand
            break
    if path is None:
        alt = Path(filename)
        if alt.exists():
            path = alt
        else:
            return {
                "ok": False,
                "error": f"فایل یافت نشد: {filename}",
                "searched": [str(d) for d in _candidate_dirs()],
            }
    data = _load_pack_file(path)
    result = apply_pack_dict(data, only_table=only_table)
    result["file"] = path.name
    result["path"] = str(path.resolve())
    return result


def apply_all_packs() -> dict:
    """اعمال همه بسته‌های JSON موجود در data/metadata/."""
    _ensure_schema()
    results = []
    files_found = []
    for d in _candidate_dirs():
        if not d.is_dir():
            continue
        jsons = sorted(d.glob("*.json"))
        if not jsons:
            continue
        for p in jsons:
            files_found.append(str(p))
            try:
                results.append(apply_pack_file(p.name))
            except Exception as e:
                log.exception("apply pack %s", p)
                results.append({"ok": False, "file": p.name, "error": str(e)})
        break  # first dir with files wins

    total_applied = sum(len(r.get("applied") or []) for r in results if r.get("ok"))
    total_cols = sum(
        sum(a.get("columns_updated") or 0 for a in (r.get("applied") or []))
        for r in results if r.get("ok")
    )
    return {
        "ok": True,
        "packs": results,
        "tables_updated": total_applied,
        "columns_updated": total_cols,
        "pack_files": len(results),
        "files_found": files_found,
        "search_dirs": [str(d) for d in _candidate_dirs()],
    }
