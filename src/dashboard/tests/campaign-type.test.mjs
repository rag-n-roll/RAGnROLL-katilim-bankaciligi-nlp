import assert from "node:assert/strict";
import test from "node:test";
import { mapCampaignType } from "../app/campaigns/campaignType.ts";

test("yalnızca kanonik ürün tipleri sekme etiketine çevrilir", () => {
  assert.equal(mapCampaignType("financing"), "Finansman");
  assert.equal(mapCampaignType("card"), "Kart");
  assert.equal(mapCampaignType("investment"), "Yatırım");
  assert.equal(mapCampaignType(null), "Belirsiz");
  assert.equal(mapCampaignType("shopping_points"), "Belirsiz");
});
