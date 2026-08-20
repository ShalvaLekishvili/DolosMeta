from __future__ import annotations

import asyncio
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from dolosmeta.config import settings
from dolosmeta.engine.analyzer import analyze_path, build_registry
from dolosmeta.engine.binary import FileSource
from dolosmeta.engine.sanitizer import SanitizationError, sanitize_file
from dolosmeta.models import AnalysisResult

app = FastAPI(title="DolosMeta API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_analyses: Dict[str, Tuple[AnalysisResult, Path]] = {}
_analyses_lock = Lock()
_cleaned_paths = set()


def _json(result: AnalysisResult) -> Dict[str, Any]:
    return result.model_dump(mode="json")


def _lookup(analysis_id: str) -> Tuple[AnalysisResult, Path]:
    with _analyses_lock:
        item = _analyses.get(analysis_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Analysis not found or expired.")
    if item[0].expires_at.timestamp() <= time.time():
        _discard(analysis_id)
        raise HTTPException(status_code=404, detail="Analysis not found or expired.")
    return item


def _discard(analysis_id: str) -> None:
    with _analyses_lock:
        item = _analyses.pop(analysis_id, None)
    if item:
        item[1].unlink(missing_ok=True)


async def _save_upload(upload: UploadFile) -> Tuple[Path, str, int]:
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    name = (upload.filename or "unnamed-file")[:1024]
    path = settings.temp_dir / (uuid4().hex + ".upload")
    size = 0
    try:
        with path.open("wb") as destination:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413, detail="file exceeds configured upload limit"
                    )
                destination.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    return path, name, size


async def _analyze_upload(upload: UploadFile) -> AnalysisResult:
    path, name, _size = await _save_upload(upload)
    try:
        result = await asyncio.to_thread(
            analyze_path,
            path,
            display_name=name,
            declared_mime=upload.content_type,
            settings=settings,
        )
    except ValueError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise
    with _analyses_lock:
        _analyses[result.id] = (result, path)
    return result


@app.get("/api/v1/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/api/v1/parsers")
async def parsers() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "parsers": [descriptor.__dict__ for descriptor in build_registry(settings).descriptors()]
    }


@app.post("/api/v1/analyze")
async def analyze(file: UploadFile = File(...)) -> Dict[str, Any]:  # noqa: B008
    return _json(await _analyze_upload(file))


@app.post("/api/v1/analyze/batch")
async def analyze_batch(  # noqa: B008
    files: List[UploadFile] = File(...),  # noqa: B008
) -> Dict[str, List[Dict[str, Any]]]:
    if not files or len(files) > settings.max_batch_files:
        raise HTTPException(status_code=413, detail="too many files for one batch")
    results = [await _analyze_upload(file) for file in files]
    return {"results": [_json(result) for result in results]}


@app.post("/api/v1/compare")
async def compare(  # noqa: B008
    file_a: UploadFile = File(...),  # noqa: B008
    file_b: UploadFile = File(...),  # noqa: B008
) -> Dict[str, Any]:
    result_a, result_b = await asyncio.gather(_analyze_upload(file_a), _analyze_upload(file_b))
    return {"file_a": _json(result_a), "file_b": _json(result_b)}


@app.get("/api/v1/analysis/{analysis_id}")
async def get_analysis(analysis_id: str) -> Dict[str, Any]:
    return _json(_lookup(analysis_id)[0])


@app.get("/api/v1/analysis/{analysis_id}/clean")
async def clean_analysis(analysis_id: str) -> FileResponse:
    result, source = _lookup(analysis_id)
    cleaned = settings.temp_dir / (uuid4().hex + ".cleaned")
    try:
        await asyncio.to_thread(sanitize_file, source, cleaned, result.file.detected_format)
    except SanitizationError as exc:
        cleaned.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _cleaned_paths.add(cleaned)
    original_name = result.file.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." in original_name:
        stem, extension = original_name.rsplit(".", 1)
        filename = stem + ".clean." + extension
    else:
        filename = original_name + ".clean"
    return FileResponse(
        cleaned,
        media_type=result.file.mime,
        filename=filename,
        headers={"X-DolosMeta-Cleaned": "metadata"},
    )


@app.get("/api/v1/analysis/{analysis_id}/{section}")
async def get_section(analysis_id: str, section: str) -> Any:
    result, _path = _lookup(analysis_id)
    if section not in {"metadata", "structure", "strings"}:
        raise HTTPException(status_code=404, detail="Unknown analysis section.")
    return getattr(result, section)


@app.get("/api/v1/analysis/{analysis_id}/hex")
async def get_hex(
    analysis_id: str,
    offset: int = Query(0, ge=0),
    length: int = Query(512, ge=1),
) -> Dict[str, Any]:
    _result, path = _lookup(analysis_id)
    length = min(length, settings.max_hex_length)
    with FileSource(path) as source:
        if offset > source.size:
            raise HTTPException(status_code=416, detail="offset exceeds file size")
        data = source.read_at(offset, min(length, source.size - offset))
        return {
            "offset": offset,
            "length": len(data),
            "total": source.size,
            "hex": data.hex(),
            "bytes": list(data),
        }


@app.get("/api/v1/analysis/{analysis_id}/export/{export_format}")
async def export_analysis(analysis_id: str, export_format: str) -> Any:
    result, _path = _lookup(analysis_id)
    if export_format != "json":
        raise HTTPException(status_code=404, detail="Only JSON export is available from the API.")
    return JSONResponse(
        content=_json(result),
        headers={"Content-Disposition": "attachment; filename=analysis.json"},
    )


@app.on_event("shutdown")
async def cleanup() -> None:
    with _analyses_lock:
        paths = [path for _result, path in _analyses.values()]
        _analyses.clear()
    for path in paths:
        path.unlink(missing_ok=True)
    for path in _cleaned_paths:
        path.unlink(missing_ok=True)
    _cleaned_paths.clear()