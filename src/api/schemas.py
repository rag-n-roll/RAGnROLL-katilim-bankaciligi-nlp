"""Versioned FastAPI request and response contracts."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt


class ApiModel(BaseModel):
    """Shared base for the versioned API contract."""


class ContractResponse(BaseModel):
    """Yeni uçların ortak izlenebilirlik alanları."""

    api_version: str = "2026.08"
    request_id: str = Field(default_factory=lambda: uuid4().hex)


class ExtractionRequest(ApiModel):
    text: str = Field(min_length=1, max_length=100_000)
    start_date: str | None = Field(default=None, max_length=50)
    end_date: str | None = Field(default=None, max_length=50)
    source_url: str | None = Field(default=None, max_length=2000)


class ExtractionResponse(ContractResponse):
    extraction: dict[str, Any]
    warnings: list[str]


class QueryCompileRequest(ApiModel):
    query: str = Field(min_length=1, max_length=2000)


class QueryCompileResponse(ContractResponse):
    plan: dict[str, Any]


class ComparisonCriteriaState(ApiModel):
    model_config = ConfigDict(extra="forbid")

    term_months: Annotated[StrictInt, Field(gt=0, le=1200)] | None = None
    amount: (
        Annotated[StrictInt | StrictFloat, Field(gt=0, le=1_000_000_000)] | None
    ) = None
    fee_priority: StrictBool | None = None


class ConversationState(ApiModel):
    model_config = ConfigDict(extra="forbid")

    pending_intent: Literal["product_comparison"]
    pending_query: str = Field(min_length=1, max_length=4000)
    criteria: ComparisonCriteriaState


class GroundedChatRequest(ApiModel):
    message: str = Field(min_length=1, max_length=4000)
    source_limit: int = Field(default=5, ge=1, le=10)
    conversation_state: ConversationState | None = None


class GroundedChatResponse(ContractResponse):
    answer: str
    action: Literal["ANSWER", "CLARIFY", "REFUSE", "REDIRECT"]
    missing_criteria: list[Literal["term_months", "amount", "fee_priority"]]
    conversation_state: ConversationState | None
    answer_display: str
    facts: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    confidence: float = Field(ge=0, le=1)
    answer_confidence: float = Field(ge=0, le=1)
    confidence_components: dict[str, float]
    warnings: list[str]
    plan: dict[str, Any]
    generation: dict[str, Any]


class MetricsSummaryResponse(ContractResponse):
    observability: dict[str, Any]
    data_quality: dict[str, Any]


class ComparisonContractResponse(ContractResponse):
    included: list[dict[str, Any]]
    excluded: list[dict[str, str]]
    pair_cache_keys: list[str]


class RecordVersionsResponse(ContractResponse):
    record_id: str
    versions: list[dict[str, Any]]


class ComparisonRequest(ApiModel):
    product_type: str = Field(min_length=1, max_length=50)
    currency: str = Field(default="TRY", min_length=3, max_length=3)
    duration_days: int | None = Field(default=None, gt=0, le=3650)
    eligibility: str | None = Field(default=None, max_length=100)
    financing_type: str | None = Field(default=None, max_length=100)
    amount: float | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, max_length=200)
    bank_slug: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=100, ge=2, le=500)


class FinancingQuoteRequest(ApiModel):
    financing_type: Literal["consumer", "vehicle", "housing", "commercial"] | None = None
    campaign_key: str | None = Field(default=None, min_length=1, max_length=100)
    amount: float = Field(gt=0, le=100_000_000)
    term_months: int = Field(ge=1, le=240)
    currency: Literal["TRY"] = "TRY"
    turkiye_finans_credit_id: int | None = Field(default=None, gt=0)


class FinancingProductRateBand(ApiModel):
    min_term_months: int = Field(ge=1)
    max_term_months: int = Field(ge=1)
    min_amount: float | None = Field(default=None, gt=0)
    max_amount: float | None = Field(default=None, gt=0)
    monthly_profit_rate: float = Field(ge=0)


class TurkiyeFinansProduct(ApiModel):
    credit_id: int = Field(gt=0)
    financing_type: Literal["consumer", "vehicle", "housing", "commercial"]
    campaign_name: str
    rate_bands: list[FinancingProductRateBand]
    source_url: str


class TurkiyeFinansProductsResponse(ApiModel):
    retrieved_at: str
    products: list[TurkiyeFinansProduct]


class FinancingCampaignBankProduct(ApiModel):
    bank_slug: str
    bank_name: str
    external_product_id: str
    campaign_name: str
    rate_bands: list[FinancingProductRateBand]
    monthly_profit_rate: float | None = Field(default=None, ge=0)
    source_url: str


class FinancingCampaign(ApiModel):
    campaign_key: str
    display_name: str
    financing_type: Literal["consumer", "vehicle", "housing", "commercial"]
    bank_products: list[FinancingCampaignBankProduct]
    availability_message: str | None = None


class FinancingCampaignsResponse(ApiModel):
    retrieved_at: str
    campaigns: list[FinancingCampaign]


class FinancingQuoteItem(ApiModel):
    bank_slug: str
    bank_name: str
    status: Literal[
        "available", "unsupported", "ineligible", "stale", "temporarily_unavailable"
    ]
    product_name: str | None = None
    monthly_profit_rate: float | None = None
    monthly_installment: float | None = None
    total_repayment: float | None = None
    annual_cost_rate: float | None = None
    fees_total: float | None = None
    source_url: str | None = None
    retrieved_at: str | None = None
    calculation_origin: str | None = None
    message: str


class FinancingCoverage(ApiModel):
    catalog_bank_count: int = Field(ge=0)
    available: int = Field(ge=0)
    unsupported: int = Field(ge=0)


class FinancingQuoteResponse(ApiModel):
    generated_at: str
    currency: Literal["TRY"]
    quotes: list[FinancingQuoteItem]
    coverage: FinancingCoverage
    disclaimer: str


class RefreshRequest(ApiModel):
    max_per_bank: int = Field(default=20, ge=1, le=100)


class HealthResponse(ApiModel):
    status: Literal["ok"]
    database: Literal["ready"]


class ScrapeRun(ApiModel):
    id: int
    started_at: str
    completed_at: str
    status: str
    record_count: int = Field(ge=0)


class DashboardSummary(ApiModel):
    campaign_count: int = Field(ge=0)
    product_count: int = Field(ge=0)
    bank_count: int = Field(ge=0)
    record_count: int = Field(ge=0)
    average_profit_share_rate: float | None = None
    last_updated_at: str | None
    campaigns_by_product_type: dict[str, int]
    latest_scrape_run: ScrapeRun | None


class BankSummaryItem(ApiModel):
    slug: str
    name: str
    website: str | None
    campaign_count: int = Field(ge=0)
    product_count: int = Field(ge=0)
    last_updated_at: str | None


class SnapshotSummary(ApiModel):
    campaign_count: int = Field(ge=0)
    product_count: int = Field(ge=0)
    bank_count: int = Field(ge=0)
    record_count: int = Field(ge=0)
    average_profit_share_rate: float | None
    last_updated_at: str | None
    campaigns_by_product_type: dict[str, int]


class BankDistributionItem(BankSummaryItem):
    record_count: int = Field(ge=0)
    campaign_share: float = Field(ge=0, le=1)
    record_share: float = Field(ge=0, le=1)


class ProductTypeDistributionItem(ApiModel):
    product_type: str
    campaign_count: int = Field(ge=0)
    product_count: int = Field(ge=0)
    record_count: int = Field(ge=0)
    share: float = Field(ge=0, le=1)


class DashboardDistributions(ApiModel):
    banks: list[BankDistributionItem]
    product_types: list[ProductTypeDistributionItem]


class DashboardFreshness(ApiModel):
    last_record_updated_at: str | None
    last_scraped_at: str | None
    campaigns_without_scraped_at: int = Field(ge=0)
    latest_scrape_run: ScrapeRun | None


class RecentCampaign(ApiModel):
    id: str
    bank_slug: str
    bank_name: str
    title: str
    source_url: str
    product_type: str | None
    updated_at: str
    scraped_at: str | None


class DashboardSnapshot(ApiModel):
    summary: SnapshotSummary
    distributions: DashboardDistributions
    freshness: DashboardFreshness
    recent_campaigns: list[RecentCampaign]


class BankSummaryResponse(ApiModel):
    items: list[BankSummaryItem]
    total: int = Field(ge=0)


class CampaignListResponse(ApiModel):
    items: list[dict[str, Any]]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class FilterOption(ApiModel):
    value: str
    label: str
    count: int = Field(ge=0)


class FilterOptionsResponse(ApiModel):
    banks: list[FilterOption]
    product_types: list[FilterOption]
    currencies: list[FilterOption]


class RefreshJobResponse(ApiModel):
    id: str
    status: Literal["queued", "running", "completed", "partial", "failed"]
    max_per_bank: int = Field(ge=1, le=100)
    return_code: int | None
    message: str
    created_at: str
    started_at: str | None
    completed_at: str | None
    timeout_seconds: float = Field(gt=0)
    output_truncated: bool
    enrichment_status: Literal[
        "disabled", "pending", "completed", "failed", "skipped"
    ] = "disabled"
    enrichment_return_code: int | None = None
    enrichment_message: str | None = None
    index_status: Literal[
        "disabled", "pending", "completed", "failed", "skipped"
    ] = "disabled"
    index_return_code: int | None = None
    index_message: str | None = None
