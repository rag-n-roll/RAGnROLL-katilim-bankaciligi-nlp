/** Select without replacement, leaving the API response untouched. */
export function sampleCampaigns<T extends { id: string }>(
  campaigns: readonly T[],
  limit = 8,
  random: () => number = Math.random,
) {
  const pool = [...new Map(campaigns.map((campaign) => [campaign.id, campaign])).values()];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, Math.max(0, limit));
}

export function initialCampaignId(rows: readonly { id: string }[], requestedId?: string) {
  return rows.find((row) => row.id === requestedId)?.id ?? rows[0]?.id ?? "";
}
