import assert from "node:assert/strict";
import test from "node:test";
import { initialCampaignId, sampleCampaigns } from "../app/campaigns/campaignSelection.ts";

test("ana sayfa değişen rastgele örnekler seçer ve kataloğu değiştirmez", () => {
  const rows = Array.from({ length: 20 }, (_, id) => ({ id: String(id) }));
  const original = structuredClone(rows);
  const first = sampleCampaigns(rows, 8, () => 0);
  const second = sampleCampaigns(rows, 8, () => 0.99);
  assert.equal(first.length, 8);
  assert.equal(new Set(first.map(row => row.id)).size, 8);
  assert.notDeepEqual(first, second);
  assert.deepEqual(rows, original);
});

test("boş ve küçük kataloglarda sahte veya tekrarlı kart üretilmez", () => {
  assert.deepEqual(sampleCampaigns([]), []);
  assert.deepEqual(sampleCampaigns([{ id: "a" }, { id: "a" }]), [{ id: "a" }]);
});

test("bağlantıdaki kampanya ilk kayıt olmasa da seçilir", () => {
  const rows = [{ id: "first" }, { id: "requested" }];
  assert.equal(initialCampaignId(rows, "requested"), "requested");
  assert.equal(initialCampaignId(rows, "deleted"), "first");
  assert.equal(initialCampaignId(rows), "first");
  assert.equal(initialCampaignId([], "deleted"), "");
});
