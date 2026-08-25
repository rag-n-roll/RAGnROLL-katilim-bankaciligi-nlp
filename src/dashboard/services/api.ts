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
    generation: ChatGeneration;
  }>("/chat", { method: "POST", body: JSON.stringify({ message }) });
}

export type ChatSource = {
  campaign_id?: string | null;
  term_id?: string | null;
  bank_name?: string | null;
  title?: string | null;
  source_url?: string | null;
  evidence?: { text: string } | null;
};

export type ChatMeta = {
  api_version: string;
  request_id: string;
  confidence: number;
  warnings: string[];
  sources: ChatSource[];
  facts: Array<Record<string, unknown>>;
  plan: { intent: string; route: string };
};

export type ChatGeneration = {
  mode: "llm" | "fallback";
  model?: string | null;
  provider?: string | null;
  requested_model?: string | null;
  fallback_reason?: string | null;
  retrieval_backend?: string;
  prompt?: { profile?: string; optimizer?: string; status?: string };
};

type StreamHandlers = {
  onMeta: (data: ChatMeta) => void;
  onDelta: (text: string) => void;
  onReplace: (text: string) => void;
  onDone: (data: ChatGeneration) => void;
};

export async function streamChat(
  message: string,
  handlers: StreamHandlers,
  signal?: AbortSignal
) {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!response.ok) {
    let detail = `API isteği başarısız oldu (${response.status}).`;
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // JSON olmayan hata yanıtında güvenli genel mesaj korunur.
    }
    throw new Error(detail);
  }
  if (!response.body) throw new Error("Tarayıcı streaming yanıtını okuyamadı.");

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = "";
  let completed = false;

  function consume(block: string) {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return;
    const data = JSON.parse(dataLines.join("\n"));
    if (event === "meta") handlers.onMeta(data as ChatMeta);
    else if (event === "delta") handlers.onDelta(String(data.text ?? ""));
    else if (event === "replace") handlers.onReplace(String(data.text ?? ""));
    else if (event === "done") {
      completed = true;
      handlers.onDone(data as ChatGeneration);
    }
    else if (event === "error") throw new Error(String(data.message ?? "Yanıt üretilemedi."));
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      consume(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (buffer.trim()) consume(buffer);
  if (!completed) {
    throw new Error("Yanıt akışı doğrulanmış bir sonuç üretmeden kesildi.");
  }
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
      enriched_evidence_coverage: number;
      verified_enrichment_fields: number;
      recovered_extraction_failures: number;
      grounded_entity_counts: Record<string, number>;
      temporal_observation_count: number;
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
