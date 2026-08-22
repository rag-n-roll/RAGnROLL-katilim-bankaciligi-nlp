"""Dashboard ve veri yenileme işlemleri için FastAPI servisi."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from threading import Lock
from typing import Annotated, Any, Callable
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from src.comparison import ComparisonQuery, compare_records
from src.persistence import CampaignStore, DashboardDataService
from src.api.schemas import (
    BankSummaryResponse,
    CampaignListResponse,
    ComparisonRequest,
    DashboardSnapshot,
    DashboardSummary,
    FilterOptionsResponse,
    HealthResponse,
    NLPAnalyzeRequest,
    RefreshJobResponse,
    RefreshRequest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = Path(os.getenv("RAGNROLL_DB_PATH", "data/ragnroll.sqlite3"))
if not DEFAULT_DATABASE.is_absolute():
    DEFAULT_DATABASE = PROJECT_ROOT / DEFAULT_DATABASE


class RefreshManager:
    """Aynı anda tek bir scraper yenilemesinin çalışmasını garanti eder."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 30 * 60,
        output_limit: int = 4000,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds pozitif olmalıdır")
        if output_limit <= 0:
            raise ValueError("output_limit pozitif olmalıdır")
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_job_id: str | None = None
        self.timeout_seconds = timeout_seconds
        self.output_limit = output_limit
        self._runner = runner

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create(self, max_per_bank: int) -> dict[str, Any] | None:
        if (
            isinstance(max_per_bank, bool)
            or not isinstance(max_per_bank, int)
            or not 1 <= max_per_bank <= 100
        ):
            raise ValueError("max_per_bank 1 ile 100 arasında olmalıdır")
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
                "created_at": self._now(),
                "started_at": None,
                "completed_at": None,
                "timeout_seconds": self.timeout_seconds,
                "output_truncated": False,
            }
            self._jobs[job_id] = job
            self._active_job_id = job_id
            return dict(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def run(self, job_id: str, database: Path) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["status"] != "queued":
                return
            job.update(
                status="running",
                started_at=self._now(),
                message="Veri yenileme çalışıyor",
            )
            max_per_bank = job["max_per_bank"]
        command = [
            sys.executable,
            "-m",
            "src.scraper.scraper",
            "--verbose",
            "collect",
            "--max-per-bank",
            str(max_per_bank),
            "--database",
            str(database.resolve()),
        ]
        try:
            runner = self._runner or subprocess.run
            result = runner(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
            message, truncated = self._bounded_output(result.stdout, result.stderr)
            status = {0: "completed", 2: "partial"}.get(
                result.returncode, "failed"
            )
            if not message:
                message = f"Scraper çıkış kodu: {result.returncode}"
            self._update(
                job_id,
                status=status,
                return_code=result.returncode,
                message=message,
                output_truncated=truncated,
            )
        except subprocess.TimeoutExpired as exc:
            output, truncated = self._bounded_output(exc.stdout, exc.stderr)
            timeout_message = (
                f"Scraper {self.timeout_seconds:g} saniye sonra zaman aşımına uğradı"
            )
            if output:
                timeout_message = f"{output}\n{timeout_message}"
            self._update(
                job_id,
                status="failed",
                message=timeout_message,
                output_truncated=truncated,
            )
        except OSError as exc:
            self._update(job_id, status="failed", message=str(exc))
        except Exception as exc:
            self._update(
                job_id,
                status="failed",
                message=f"Scraper beklenmeyen bir hatayla durdu: {exc}",
            )
        finally:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job["completed_at"] = self._now()
                if self._active_job_id == job_id:
                    self._active_job_id = None

    def _bounded_output(
        self, stdout: str | bytes | None, stderr: str | bytes | None
    ) -> tuple[str, bool]:
        def as_text(value: str | bytes | None) -> str:
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return value or ""

        output = "\n".join(
            part.strip() for part in (as_text(stdout), as_text(stderr)) if part.strip()
        )
        if len(output) <= self.output_limit:
            return output, False
        marker = "[çıktının başı sınır nedeniyle kesildi]\n"
        if self.output_limit <= len(marker):
            return output[-self.output_limit :], True
        return marker + output[-(self.output_limit - len(marker)) :], True

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


def _nlp_pipeline(request: Request) -> Any:
    pipeline = getattr(request.app.state, "nlp_pipeline", None)
    if pipeline is not None:
        return pipeline
    lock = getattr(request.app.state, "nlp_pipeline_lock", None)
    if lock is None:
        lock = Lock()
        request.app.state.nlp_pipeline_lock = lock
    with lock:
        pipeline = getattr(request.app.state, "nlp_pipeline", None)
        if pipeline is None:
            from src.extraction.campaign_nlp_pipeline import CampaignNLPPipeline

            classifier = os.getenv(
                "RAGNROLL_CLASSIFIER_MODEL",
                "models/final_training/campaign_classifier.joblib",
            )
            ner = os.getenv(
                "RAGNROLL_NER_MODEL",
                "models/final_training/augmented_weighted_30e",
            )
            classifier_path = Path(classifier)
            ner_path = Path(ner)
            if not classifier_path.is_absolute():
                classifier_path = PROJECT_ROOT / classifier_path
            if not ner_path.is_absolute():
                ner_path = PROJECT_ROOT / ner_path
            try:
                pipeline = CampaignNLPPipeline.load(classifier_path, ner_path)
            except (OSError, ImportError, ValueError) as exc:
                raise HTTPException(
                    status_code=503, detail=f"NLP modelleri yüklenemedi: {exc}"
                ) from exc
            request.app.state.nlp_pipeline = pipeline
    return pipeline


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> dict[str, Any]:
    store = _store(request)
    store.initialize()
    return {"status": "ok", "database": "ready"}


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummary,
    tags=["dashboard"],
)
def dashboard_summary(request: Request) -> dict[str, Any]:
    store = _store(request)
    return {
        **store.dashboard_summary(),
        "latest_scrape_run": store.latest_scrape_run(),
    }


@router.get(
    "/dashboard/snapshot",
    response_model=DashboardSnapshot,
    tags=["dashboard"],
)
def dashboard_snapshot(
    request: Request,
    recent_limit: Annotated[int, Query(ge=1, le=50)] = 5,
) -> dict[str, Any]:
    """Return the dashboard's complete initial payload in one request."""
    return DashboardDataService(_store(request)).snapshot(recent_limit=recent_limit)


@router.get("/banks", response_model=BankSummaryResponse, tags=["dashboard"])
def banks(request: Request) -> dict[str, Any]:
    items = _store(request).bank_summary()
    return {"items": items, "total": len(items)}


@router.get(
    "/campaigns",
    response_model=CampaignListResponse,
    tags=["campaigns"],
)
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


@router.get("/filters", response_model=FilterOptionsResponse, tags=["dashboard"])
def filter_options(request: Request) -> dict[str, Any]:
    """Return canonical, counted choices for dashboard filter controls."""
    return _store(request).filter_options()


@router.get("/campaigns/{campaign_id}", tags=["campaigns"])
def campaign_detail(campaign_id: str, request: Request) -> dict[str, Any]:
    campaign = _store(request).get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    return campaign


@router.post("/comparisons", tags=["comparisons"])
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


@router.post("/nlp/analyze")
def analyze_campaign(payload: NLPAnalyzeRequest, request: Request) -> dict[str, Any]:
    """Classify a campaign and extract normalized entities in one request."""
    return _nlp_pipeline(request).analyze(
        payload.text,
        record_id=payload.record_id,
        title=payload.title,
        source_url=payload.source_url,
    )


@router.post(
    "/data-refresh",
    status_code=202,
    response_model=RefreshJobResponse,
    tags=["data-refresh"],
)
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


@router.get(
    "/data-refresh/{job_id}",
    response_model=RefreshJobResponse,
    tags=["data-refresh"],
)
def data_refresh_status(job_id: str, request: Request) -> dict[str, Any]:
    job = _refresh_manager(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Veri yenileme işi bulunamadı")
    return job


def create_app(*, database_path: str | Path | None = None) -> FastAPI:
    api = FastAPI(
        title="RAGnROLL Katılım Bankacılığı API",
        version="0.4.0",
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
    api.state.nlp_pipeline = None
    api.state.nlp_pipeline_lock = Lock()
    api.include_router(router)
    return api


app = create_app()
