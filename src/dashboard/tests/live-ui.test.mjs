import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const dashboardRoot = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, dashboardRoot), "utf8");
}

test("sayfalar canlı API sözleşmelerini korur", async () => {
  const [home, campaigns, compare, chatbot] = await Promise.all([
    source("app/page.tsx"),
    source("app/campaigns/page.tsx"),
    source("app/compare/page.tsx"),
    source("app/chatbot/page.tsx"),
  ]);

  assert.match(home, /getDashboardSnapshot\(\)/);
  assert.match(campaigns, /getFilters\(\)/);
  assert.match(campaigns, /getCampaigns\(/);
  assert.match(campaigns, /getCampaignDetail\(/);
  assert.match(compare, /compareCampaigns\(/);
  assert.match(compare, /getFilters\(\)/);
  assert.match(chatbot, /streamChat\(/);
  for (const handler of ["onMeta", "onDelta", "onReplace", "onDone"]) {
    assert.match(chatbot, new RegExp(`${handler}:`));
  }
});

test("sohbet abort ve eksik EOF durumunda doğrulanmamış cevabı temizler", async () => {
  const [chatbot, api] = await Promise.all([
    source("app/chatbot/page.tsx"),
    source("services/api.ts"),
  ]);

  assert.match(chatbot, /if \(!completed\)/);
  assert.match(chatbot, /answer: ""/);
  assert.match(chatbot, /generation: undefined/);
  assert.match(api, /if \(!completed\)/);
  assert.match(api, /doğrulanmış bir sonuç üretmeden kesildi/);
});

test("yeni sohbet yalnız istemci durumunu sıfırlar", async () => {
  const chatbot = await source("app/chatbot/page.tsx");

  assert.match(chatbot, /Yeni sohbet/);
  assert.match(chatbot, /aria-label="Yeni sohbet başlat"/);
  assert.match(chatbot, /activeController\?\.abort\(\)/);
  assert.match(chatbot, /messageInput\.current\?\.focus\(\)/);
  assert.doesNotMatch(chatbot, /\/api\/reset/);
});

test("chatbot arayüzü sağlayıcı veya model adı göstermez", async () => {
  const [chatbot, quality] = await Promise.all([
    source("app/chatbot/page.tsx"),
    source("app/quality/page.tsx"),
  ]);

  assert.doesNotMatch(chatbot, /Gemma|EVREN|\bmodel\b/i);
  assert.doesNotMatch(quality, /Gemma|EVREN|llm-(?:fast|large)|\bmodel\b/i);
  assert.match(chatbot, /Kanıta bağlı üretim/);
});

test("kalite sayfası doğrulanmış bağlam ve gözlem tarihini açıklar", async () => {
  const quality = await source("app/quality/page.tsx");

  assert.match(quality, /Doğrulanmış bağlam varlıkları/);
  assert.match(quality, /Kart adı/);
  assert.match(quality, /temporal_observation_count/);
  assert.match(quality, /yalnız kaynakta görülme kanıtı/);
});

test("arayüz statik sahte veri veya PR26 hero görseli taşımaz", async () => {
  const pages = await Promise.all([
    source("app/page.tsx"),
    source("app/campaigns/page.tsx"),
    source("app/compare/page.tsx"),
    source("app/chatbot/page.tsx"),
  ]);
  const renderedUi = pages.join("\n");

  for (const banned of [
    "ComparisonCharts",
    "CampaignDistributionChart",
    "fs.readFileSync",
    "pusula-hero",
    "Sorunuzu aldım",
    "%2,49",
    "471 kampanya",
  ]) {
    assert.doesNotMatch(renderedUi, new RegExp(banned, "i"));
  }
  assert.doesNotMatch(pages[0], /\.(?:png|jpe?g|webp)/i);
});

test("klavye, canlı bölge, sonuç odağı ve responsive kuralları görünürdür", async () => {
  const [campaigns, compare, chatbot, liveCss, globals] = await Promise.all([
    source("app/campaigns/page.tsx"),
    source("app/compare/page.tsx"),
    source("app/chatbot/page.tsx"),
    source("app/live.module.css"),
    source("app/globals.css"),
  ]);

  assert.match(campaigns, /aria-pressed=/);
  assert.match(compare, /resultRef\.current\?\.focus\(\)/);
  assert.match(compare, /tabIndex=\{-1\}/);
  assert.match(chatbot, /role="log"/);
  assert.match(chatbot, /aria-live="polite"/);
  assert.match(chatbot, /htmlFor="chat-message"/);
  assert.match(chatbot, /id="chat-message"/);
  assert.match(liveCss, /@media \(max-width: 520px\)/);
  assert.match(liveCss, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(liveCss, /overflow-x: auto/);
  assert.match(globals, /:focus-visible/);
});

test("kampanya kataloğu artımlı sayfalama ve temiz metin sunumu kullanır", async () => {
  const campaigns = await source("app/campaigns/page.tsx");

  assert.match(campaigns, /const PAGE_SIZES = \[10, 50\]/);
  assert.match(campaigns, /offset: campaigns\.length/);
  assert.match(campaigns, /kampanya daha göster/);
  assert.match(campaigns, /formatCampaignContent/);
  assert.doesNotMatch(campaigns, /className=\{styles\.code\}/);
});
