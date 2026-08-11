"""Dashboard ve veri yenileme işlemleri için FastAPI servisi."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from threading import Lock
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.comparison import ComparisonQuery, compare_records
from src.persistence import CampaignStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = Path(os.getenv("RAGNROLL_DB_PATH", "data/ragnroll.sqlite3"))
if not DEFAULT_DATABASE.is_absolute():
    DEFAULT_DATABASE = PROJECT_ROOT / DEFAULT_DATABASE


class ComparisonRequest(BaseModel):
    product_type: str = Field(min_length=1, max_length=50)
    currency: str = Field(default="TRY", min_length=3, max_length=3)
    duration_days: int | None = Field(default=None, gt=0, le=3650)
    eligibility: str | None = Field(default=None, max_length=100)
    financing_type: str | None = Field(default=None, max_length=100)
    amount: float | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, max_length=200)
    bank_slug: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=100, ge=2, le=500)


class RefreshRequest(BaseModel):
    max_per_bank: int = Field(default=20, ge=1, le=100)


class RefreshManager:
    """Aynı anda tek bir scraper yenilemesinin çalışmasını garanti eder."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_job_id: str | None = None

    def create(self, max_per_bank: int) -> dict[str, Any] | None:
        with self._lock:
            if self._active_job_id is not None:
                return None
            job_id = uuid4().hex
            job = {
                "id": job_id,
                "status": "queued",
                "max_per_bank": max_per_bank,
                "return_code": None,
                "message": "Veri yenileme sıraya alındı",
            }
            self._jobs[job_id] = job
            self._active_job_id = job_id
            return dict(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def run(self, job_id: str, database: Path) -> None:
        self._update(job_id, status="running", message="Veri yenileme çalışıyor")
        command = [
            sys.executable,
            "-m",
            "src.scraper.scraper",
            "--verbose",
            "collect",
            "--max-per-bank",
            str(self._jobs[job_id]["max_per_bank"]),
            "--database",
            str(database),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            output = (result.stdout or result.stderr).strip()
            status = "completed" if result.returncode == 0 else "failed"
            message = output[-2000:] or f"Scraper çıkış kodu: {result.returncode}"
            self._update(
                job_id,
                status=status,
                return_code=result.returncode,
                message=message,
            )
        except OSError as exc:
            self._update(job_id, status="failed", message=str(exc))
        finally:
            with self._lock:
                self._active_job_id = None

    def _update(self, job_id: str, **values: Any) -> None:
        with self._lock:
            self._jobs[job_id].update(values)


router = APIRouter(prefix="/api/v1")


def _store(request: Request) -> CampaignStore:
    path = getattr(request.app.state, "database_path", DEFAULT_DATABASE)
    return CampaignStore(path)


def _refresh_manager(request: Request) -> RefreshManager:
    manager = getattr(request.app.state, "refresh_manager", None)
    if manager is None:
        manager = RefreshManager()
        request.app.state.refresh_manager = manager
    return manager


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    store = _store(request)
    store.initialize()
    return {"status": "ok", "database": "ready"}


@router.get("/dashboard/summary")
def dashboard_summary(request: Request) -> dict[str, Any]:
    store = _store(request)
    return {
        **store.dashboard_summary(),
        "latest_scrape_run": store.latest_scrape_run(),
    }


@router.get("/banks")
def banks(request: Request) -> dict[str, Any]:
    items = _store(request).bank_summary()
    return {"items": items, "total": len(items)}


@router.get("/campaigns")
def campaigns(
    request: Request,
    bank_slug: str | None = None,
    product_type: str | None = None,
    currency: Annotated[str | None, Query(min_length=3, max_length=3)] = None,
    search: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items, total = _store(request).query_campaigns(
        bank_slug=bank_slug,
        product_type=product_type,
        currency=currency.upper() if currency else None,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/campaigns/{campaign_id}")
def campaign_detail(campaign_id: str, request: Request) -> dict[str, Any]:
    campaign = _store(request).get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    return campaign


@router.post("/comparisons")
def comparisons(payload: ComparisonRequest, request: Request) -> dict[str, Any]:
    records, total = _store(request).query_campaigns(
        bank_slug=payload.bank_slug,
        product_type=payload.product_type,
        currency=payload.currency.upper(),
        limit=payload.limit,
    )
    if total > payload.limit:
        raise HTTPException(
            status_code=422,
            detail=f"Karşılaştırma {payload.limit} kayıtla sınırlı; filtreleri daraltın",
        )
    result = compare_records(
        records,
        ComparisonQuery(
            product_type=payload.product_type,
            currency=payload.currency.upper(),
            duration_days=payload.duration_days,
            eligibility=payload.eligibility,
            financing_type=payload.financing_type,
            amount=payload.amount,
            title=payload.title,
        ),
    )
    return result.to_dict()


@router.post("/data-refresh", status_code=202)
def start_data_refresh(
    payload: RefreshRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    manager = _refresh_manager(request)
    job = manager.create(payload.max_per_bank)
    if job is None:
        raise HTTPException(status_code=409, detail="Bir veri yenileme zaten çalışıyor")
    background_tasks.add_task(manager.run, job["id"], _store(request).path)
    return job


@router.get("/data-refresh/{job_id}")
def data_refresh_status(job_id: str, request: Request) -> dict[str, Any]:
    job = _refresh_manager(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Veri yenileme işi bulunamadı")
    return job


def create_app(*, database_path: str | Path | None = None) -> FastAPI:
    api = FastAPI(
        title="RAGnROLL Katılım Bankacılığı API",
        version="0.3.0",
        description="Dashboard, kampanya karşılaştırma ve veri yenileme servisi.",
    )
    origins = [
        value.strip()
        for value in os.getenv("RAGNROLL_CORS_ORIGINS", "http://localhost:3000").split(",")
        if value.strip()
    ]
    api.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    api.state.database_path = Path(database_path) if database_path else DEFAULT_DATABASE
    api.state.refresh_manager = RefreshManager()
    api.include_router(router)
    return api


app = create_app()
