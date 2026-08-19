const API_BASE_URL = "http://localhost:8000/api/v1";

async function apiRequest<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const errorText = await response.text();

    throw new Error(
      errorText || `API isteği başarısız oldu. Status: ${response.status}`
    );
  }

  return response.json();
}

export async function getHealth() {
  return apiRequest("/health");
}

export async function getDashboardSummary() {
  return apiRequest("/dashboard/summary");
}

export async function getBanks() {
  return apiRequest("/banks");
}

export type CampaignFilters = {
  bank_slug?: string;
  product_type?: string;
  currency?: string;
  search?: string;
  limit?: number;
  offset?: number;
};

export async function getCampaigns(filters: CampaignFilters = {}) {
  const params = new URLSearchParams();

  if (filters.bank_slug) {
    params.append("bank_slug", filters.bank_slug);
  }

  if (filters.product_type) {
    params.append("product_type", filters.product_type);
  }

  if (filters.currency) {
    params.append("currency", filters.currency);
  }

  if (filters.search) {
    params.append("search", filters.search);
  }

  if (filters.limit !== undefined) {
    params.append("limit", filters.limit.toString());
  }

  if (filters.offset !== undefined) {
    params.append("offset", filters.offset.toString());
  }

  const queryString = params.toString();

  return apiRequest(
    `/campaigns${queryString ? `?${queryString}` : ""}`
  );
}

export async function getCampaignDetail(campaignId: string) {
  return apiRequest(`/campaigns/${campaignId}`);
}

export type ComparisonRequest = {
  bank_slug?: string;
  product_type?: string;
  currency?: string;
  duration_days?: number;
  eligibility?: string;
  financing_type?: string;
  amount?: number;
  title?: string;
  limit?: number;
};

export async function compareCampaigns(payload: ComparisonRequest) {
  return apiRequest("/comparisons", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type DataRefreshRequest = {
  max_per_bank?: number;
};

export async function startDataRefresh(
  payload: DataRefreshRequest = {}
) {
  return apiRequest("/data-refresh", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getDataRefreshStatus(jobId: string) {
  return apiRequest(`/data-refresh/${jobId}`);
}