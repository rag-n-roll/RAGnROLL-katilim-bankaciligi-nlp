"""Dashboard ve veri yenileme işlemleri için FastAPI servisi."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from threading import Lock
from time import perf_counter
from typing import Annotated, Any, Callable
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from src.comparison import ComparisonQuery, compare_records
from src.extraction.hybrid import HybridExtractor
from src.observability import EventRecorder
from src.persistence import CampaignStore, DashboardDataService
from src.query import DomainQueryCompiler
from src.services import GroundedAssistant
from src.api.schemas import (
    BankSummaryResponse,
    CampaignListResponse,
    ComparisonRequest,
    ComparisonContractResponse,
    DashboardSnapshot,
    DashboardSummary,
    ExtractionRequest,
    ExtractionResponse,
    FilterOptionsResponse,
    GroundedChatRequest,
    GroundedChatResponse,
    HealthResponse,
    MetricsSummaryResponse,
    QueryCompileRequest,
    QueryCompileResponse,
    RecordVersionsResponse,
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
        enrich_timeout_seconds: float = 30 * 60,
        index_timeout_seconds: float = 60 * 60,
        output_limit: int = 4000,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        auto_enrich: bool | None = None,
        auto_index: bool | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds pozitif olmalıdır")
        if output_limit <= 0:
            raise ValueError("output_limit pozitif olmalıdır")
        if enrich_timeout_seconds <= 0:
            raise ValueError("enrich_timeout_seconds pozitif olmalıdır")
        if index_timeout_seconds <= 0:
            raise ValueError("index_timeout_seconds pozitif olmalıdır")
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_job_id: str | None = None
        self.timeout_seconds = timeout_seconds
        self.enrich_timeout_seconds = enrich_timeout_seconds
        self.index_timeout_seconds = index_timeout_seconds
        self.output_limit = output_limit
        self._runner = runner
        if auto_enrich is None:
            configured = os.getenv("RAGNROLL_NLP_AUTO_ENRICH", "false").casefold()
            auto_enrich = configured not in {"0", "false", "off", "hayır", "hayir"}
        self.auto_enrich = auto_enrich
        if auto_index is None:
            configured = os.getenv("RAGNROLL_CHROMA_AUTO_INDEX", "false").casefold()
            auto_index = configured not in {"0", "false", "off", "hayır", "hayir"}
        self.auto_index = auto_index

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _runtime_path(*parts: str) -> Path:
        root = Path(os.getenv("RAGNROLL_RUNTIME_ROOT", str(PROJECT_ROOT)))
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        return root.joinpath(*parts)

    def _refresh_command(self, max_per_bank: int, database: Path) -> list[str]:
        banks_output = self._runtime_path("data", "raw", "participation_banks.json")
        raw_output = self._runtime_path("data", "raw", "campaigns.json")
        processed_output = self._runtime_path("data", "processed", "campaigns.json")
        quality_report = self._runtime_path("outputs", "quality_report.json")
        configured_dataset = os.getenv("RAGNROLL_REFRESH_DATASET", "").strip()
        if configured_dataset:
            dataset = Path(configured_dataset)
            if not dataset.is_absolute():
                dataset = PROJECT_ROOT / dataset
            return [
                sys.executable,
                "-m",
                "src.scraper.scraper",
                "db",
                "import-json",
                str(dataset.resolve()),
                "--database",
                str(database.resolve()),
                "--raw-output",
                str(raw_output),
                "--processed-output",
                str(processed_output),
            ]
        return [
            sys.executable,
            "-m",
            "src.scraper.scraper",
            "--verbose",
            "collect",
            "--max-per-bank",
            str(max_per_bank),
            "--database",
            str(database.resolve()),
            "--banks-output",
            str(banks_output),
            "--raw-output",
            str(raw_output),
            "--processed-output",
            str(processed_output),
            "--quality-report",
            str(quality_report),
        ]

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
                "enrichment_status": "pending" if self.auto_enrich else "disabled",
                "enrichment_return_code": None,
                "enrichment_message": None,
                "index_status": "pending" if self.auto_index else "disabled",
                "index_return_code": None,
                "index_message": None,
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
        command = self._refresh_command(max_per_bank, database)
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
            enrichment_values: dict[str, Any] = {}
            index_values: dict[str, Any] = {}
            if status in {"completed", "partial"} and self.auto_enrich:
                enrichment_values = self._run_enrichment(database)
                enrichment_message = str(
                    enrichment_values.get("enrichment_message") or ""
                )
                if enrichment_values.get("enrichment_status") == "failed":
                    status = "partial"
                    message = (
                        f"{message}\nNLP zenginleştirmesi tamamlanamadı: "
                        f"{enrichment_message}"
                    )
            elif self.auto_enrich:
                enrichment_values = self._skipped_enrichment()
            if status in {"completed", "partial"} and self.auto_index:
                index_values = self._run_index(database)
                index_message = str(index_values.get("index_message") or "")
                if index_values.get("index_status") == "failed":
                    status = "partial"
                    message = f"{message}\nİndeks güncellenemedi: {index_message}"
            elif self.auto_index:
                index_values = {
                    "index_status": "skipped",
                    "index_message": (
                        "Veri yenilemesi başarısız olduğu için indeks çalıştırılmadı"
                    ),
                }
            self._update(
                job_id,
                status=status,
                return_code=result.returncode,
                message=message,
                output_truncated=truncated,
                **enrichment_values,
                **index_values,
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
                **self._skipped_enrichment(),
                **self._skipped_index(),
            )
        except OSError as exc:
            self._update(
                job_id,
                status="failed",
                message=str(exc),
                **self._skipped_enrichment(),
                **self._skipped_index(),
            )
        except Exception as exc:
            self._update(
                job_id,
                status="failed",
                message=f"Scraper beklenmeyen bir hatayla durdu: {exc}",
                **self._skipped_enrichment(),
                **self._skipped_index(),
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

    def _run_index(self, database: Path) -> dict[str, Any]:
        command = [
            sys.executable,
            "-m",
            "scripts.ingest_chroma",
            "--database",
            str(database.resolve()),
            "--batch-size",
            os.getenv("RAGNROLL_INDEX_BATCH_SIZE", "64"),
        ]
        if os.getenv("RAGNROLL_INDEX_SMOKE", "false").casefold() not in {
            "0",
            "false",
            "off",
            "hayır",
            "hayir",
        }:
            command.append("--smoke")
        try:
            runner = self._runner or subprocess.run
            result = runner(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.index_timeout_seconds,
            )
            message, _ = self._bounded_output(result.stdout, result.stderr)
            return {
                "index_status": "completed" if result.returncode == 0 else "failed",
                "index_return_code": result.returncode,
                "index_message": message or f"İndeks çıkış kodu: {result.returncode}",
            }
        except subprocess.TimeoutExpired as exc:
            output, _ = self._bounded_output(exc.stdout, exc.stderr)
            message = f"İndeks {self.index_timeout_seconds:g} saniye sonra zaman aşımına uğradı"
            return {
                "index_status": "failed",
                "index_return_code": None,
                "index_message": f"{output}\n{message}" if output else message,
            }
        except OSError as exc:
            return {
                "index_status": "failed",
                "index_return_code": None,
                "index_message": str(exc),
            }
        except Exception as exc:
            return {
                "index_status": "failed",
                "index_return_code": None,
                "index_message": f"İndeks beklenmeyen bir hatayla durdu: {exc}",
            }

    def _run_enrichment(self, database: Path) -> dict[str, Any]:
        command = [
            sys.executable,
            "-m",
            "scripts.enrich_nlp",
            "--database",
            str(database.resolve()),
        ]
        manifest = os.getenv("RAGNROLL_NLP_MANIFEST", "").strip()
        if manifest:
            command.extend(("--manifest", manifest))
        max_records = os.getenv("RAGNROLL_NLP_MAX_RECORDS", "").strip()
        if max_records and max_records != "0":
            command.extend(("--max-records", max_records))
        try:
            runner = self._runner or subprocess.run
            result = runner(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.enrich_timeout_seconds,
            )
            message, _ = self._bounded_output(result.stdout, result.stderr)
            return {
                "enrichment_status": (
                    "completed" if result.returncode == 0 else "failed"
                ),
                "enrichment_return_code": result.returncode,
                "enrichment_message": (
                    message or f"NLP zenginleştirme çıkış kodu: {result.returncode}"
                ),
            }
        except subprocess.TimeoutExpired as exc:
            output, _ = self._bounded_output(exc.stdout, exc.stderr)
            message = (
                "NLP zenginleştirmesi "
                f"{self.enrich_timeout_seconds:g} saniye sonra zaman aşımına uğradı"
            )
            return {
                "enrichment_status": "failed",
                "enrichment_return_code": None,
                "enrichment_message": f"{output}\n{message}" if output else message,
            }
        except OSError as exc:
            return {
                "enrichment_status": "failed",
                "enrichment_return_code": None,
                "enrichment_message": str(exc),
            }
        except Exception as exc:
            return {
                "enrichment_status": "failed",
                "enrichment_return_code": None,
                "enrichment_message": (
                    f"NLP zenginleştirmesi beklenmeyen bir hatayla durdu: {exc}"
                ),
            }

    def _skipped_enrichment(self) -> dict[str, Any]:
        if not self.auto_enrich:
            return {}
        return {
            "enrichment_status": "skipped",
            "enrichment_message": (
                "Veri yenilemesi tamamlanamadığı için NLP zenginleştirmesi çalıştırılmadı"
            ),
        }

    def _skipped_index(self) -> dict[str, Any]:
        if not self.auto_index:
            return {}
        return {
            "index_status": "skipped",
            "index_message": "Veri yenilemesi tamamlanamadığı için indeks çalıştırılmadı",
        }

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


def _recorder(request: Request) -> EventRecorder:
    recorder = getattr(request.app.state, "event_recorder", None)
    if recorder is None:
        recorder = EventRecorder()
        request.app.state.event_recorder = recorder
    return recorder


def _assistant(request: Request) -> GroundedAssistant:
    assistant = getattr(request.app.state, "grounded_assistant", None)
    if assistant is None:
        assistant = GroundedAssistant(
            _store(request),
            recorder=_recorder(request),
            chroma_enabled=getattr(request.app.state, "chroma_enabled", None),
        )
        request.app.state.grounded_assistant = assistant
    return assistant


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


@router.get(
    "/campaigns/{campaign_id}/versions",
    response_model=RecordVersionsResponse,
    tags=["campaigns"],
)
def campaign_versions(campaign_id: str, request: Request) -> dict[str, Any]:
    if _store(request).get_campaign(campaign_id) is None:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    return {
        "record_id": campaign_id,
        "versions": _store(request).record_versions(campaign_id),
    }


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


@router.post(
    "/compare",
    response_model=ComparisonContractResponse,
    tags=["comparisons"],
)
def compare_contract(payload: ComparisonRequest, request: Request) -> dict[str, Any]:
    return comparisons(payload, request)


@router.post(
    "/extract",
    response_model=ExtractionResponse,
    tags=["nlp"],
)
def extract(payload: ExtractionRequest, request: Request) -> dict[str, Any]:
    started = perf_counter()
    success = True
    try:
        extraction = HybridExtractor().extract(
            payload.text,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        warnings = [
            f"{name}: {field['status']}"
            for name, field in extraction.get("fields", {}).items()
            if field.get("status") in {"EXTRACTION_FAILED", "CONFLICT"}
        ]
        return {"extraction": extraction, "warnings": warnings}
    except Exception:
        success = False
        raise
    finally:
        _recorder(request).record(
            "extraction_completed",
            latency_ms=(perf_counter() - started) * 1000,
            success=success,
            field_count=(
                len(extraction.get("fields", {}))
                if success and "extraction" in locals()
                else 0
            ),
        )


@router.post(
    "/query/compile",
    response_model=QueryCompileResponse,
    tags=["query"],
)
def compile_query(payload: QueryCompileRequest, request: Request) -> dict[str, Any]:
    started = perf_counter()
    success = True
    route = "UNKNOWN"
    try:
        plan = DomainQueryCompiler().compile(
            payload.query,
            known_banks=_store(request).bank_summary(),
        )
        route = plan.route
        return {"plan": plan.to_dict()}
    except ValueError as exc:
        success = False
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        _recorder(request).record(
            "query_compiled",
            latency_ms=(perf_counter() - started) * 1000,
            success=success,
            route=route,
        )


@router.post(
    "/chat",
    response_model=GroundedChatResponse,
    tags=["chatbot"],
)
def grounded_chat(payload: GroundedChatRequest, request: Request) -> dict[str, Any]:
    try:
        return _assistant(request).answer(payload.message, limit=payload.source_limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/chat/stream",
    tags=["chatbot"],
    response_class=StreamingResponse,
)
def grounded_chat_stream(
    payload: GroundedChatRequest, request: Request
) -> StreamingResponse:
    """Yanıt metnini ve kaynak meta verisini SSE olaylarıyla aktarır."""

    request_id = uuid4().hex

    def events():
        try:
            for item in _assistant(request).stream_answer(
                payload.message, limit=payload.source_limit
            ):
                data = dict(item["data"])
                if item["event"] == "meta":
                    data.update(api_version="2026.08", request_id=request_id)
                yield (
                    f"event: {item['event']}\n"
                    f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                )
        except ValueError as exc:
            yield (
                "event: error\n"
                f"data: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/llm/status", tags=["system"])
def llm_status(request: Request) -> dict[str, Any]:
    return _assistant(request).llm.status()


@router.get(
    "/metrics/summary",
    response_model=MetricsSummaryResponse,
    tags=["system"],
)
def metrics_summary(request: Request) -> dict[str, Any]:
    return {
        "observability": _recorder(request).summary(),
        "data_quality": _store(request).data_quality_summary(),
    }


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


def create_app(
    *,
    database_path: str | Path | None = None,
    chroma_enabled: bool | None = None,
) -> FastAPI:
    api = FastAPI(
        title="RAGnROLL Katılım Bankacılığı API",
        version="0.4.0",
        description="Dashboard, kampanya karşılaştırma ve veri yenileme servisi.",
    )
    origins = [
        value.strip()
        for value in os.getenv(
            "RAGNROLL_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
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
    api.state.chroma_enabled = (
        chroma_enabled if chroma_enabled is not None else database_path is None
    )
    api.state.refresh_manager = RefreshManager()
    api.state.event_recorder = EventRecorder()
    api.include_router(router)
    return api


app = create_app()
