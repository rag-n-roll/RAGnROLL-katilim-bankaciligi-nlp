const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type FieldContract = {
  raw: string | null;
  value: unknown;
  unit: string | null;
  status: string;
  confidence: number;
  evidence: { text: string; char_start: number | null; char_end: number | null } | null;
};

export type Campaign = {
  id: string;
  bank_slug: string;
  bank_name: string;
  title: string;
  content: string;
  source_url: string;
  scraped_at?: string | null;
  structured?: Record<string, unknown> & { fields?: Record<string, FieldContract> };
};

export type FilterOption = { value: string; label: string; count: number };

async function apiRequest<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    let message = `API isteği başarısız oldu (${response.status}).`;
    try {
      const payload = await response.json();
      message = payload.detail ?? message;
    } catch {
      // JSON olmayan hata yanıtında güvenli genel mesajı koru.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function getHealth() {
  return apiRequest<{ status: string; database: string }>("/health");
}

export function getDashboardSnapshot() {
  return apiRequest<{
    summary: {
      campaign_count: number;
      bank_count: number;
      record_count: number;
      average_profit_share_rate: number | null;
      last_updated_at: string | null;
    };
    distributions: {
      banks: Array<{
        slug: string;
        name: string;
        campaign_count: number;
        campaign_share: number;
      }>;
    };
    recent_campaigns: Array<{
      id: string;
      bank_name: string;
      title: string;
      product_type: string | null;
      updated_at: string;
    }>;
  }>("/dashboard/snapshot?recent_limit=8");
}

export function getFilters() {
  return apiRequest<{
    banks: FilterOption[];
    product_types: FilterOption[];
    currencies: FilterOption[];
  }>("/filters");
}

export type CampaignFilters = {
  bank_slug?: string;
  product_type?: string;
  currency?: string;
  search?: string;
  limit?: number;
  offset?: number;
};

export function getCampaigns(filters: CampaignFilters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return apiRequest<{
    items: Campaign[];
    total: number;
    limit: number;
    offset: number;
  }>(`/campaigns${params.size ? `?${params}` : ""}`);
}

export function getCampaignDetail(campaignId: string) {
  return apiRequest<Campaign>(`/campaigns/${encodeURIComponent(campaignId)}`);
}

export type ComparisonRequest = {
  bank_slug?: string;
  product_type: string;
  currency?: string;
  duration_days?: number;
  eligibility?: string;
  financing_type?: string;
  amount?: number;
  title?: string;
  limit?: number;
};

export function compareCampaigns(payload: ComparisonRequest) {
  return apiRequest<{
    included: Array<{
      id: string;
      title: string;
      match_score: number;
      advantage_score: number | null;
      comparison_confidence: number;
      missing_fields: string[];
      ranking_reason: string;
    }>;
    excluded: Array<{ id: string; reason: string }>;
  }>("/compare", { method: "POST", body: JSON.stringify(payload) });
}

export function compileQuery(query: string) {
  return apiRequest<{
    plan: { intent: string; route: string; confidence: number };
  }>("/query/compile", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}

export function sendChat(message: string) {
  return apiRequest<{
    answer: string;
    confidence: number;
    warnings: string[];
    sources: Array<{
      campaign_id?: string | null;
      term_id?: string | null;
      bank_name?: string | null;
      title?: string | null;
      source_url?: string | null;
      evidence?: { text: string } | null;
    }>;
    plan: { intent: string; route: string };
  }>("/chat", { method: "POST", body: JSON.stringify({ message }) });
}

export function getMetricsSummary() {
  return apiRequest<{
    observability: {
      event_count: number;
      events: Record<
        string,
        {
          count: number;
          error_rate: number;
          p50_latency_ms: number | null;
          p95_latency_ms: number | null;
        }
      >;
    };
    data_quality: {
      record_count: number;
      duplicate_cluster_count: number;
      field_statuses: Record<string, number>;
      evidence_coverage: number;
    };
  }>("/metrics/summary");
}

export function startDataRefresh(max_per_bank = 20) {
  return apiRequest<{ id: string; status: string }>("/data-refresh", {
    method: "POST",
    body: JSON.stringify({ max_per_bank }),
  });
}

export function getDataRefreshStatus(jobId: string) {
  return apiRequest<{ id: string; status: string; message: string }>(
    `/data-refresh/${encodeURIComponent(jobId)}`
  );
}
