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

  assert.match(home, /getDashboardSnapshot/);
  assert.match(campaigns, /getCampaigns/);
  assert.match(compare, /compareCampaigns/);
  assert.match(chatbot, /streamChat/);
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
  assert.match(chatbot, /answer(?: =|:)\s*""/);
  assert.match(chatbot, /generation(?: =|:)\s*undefined/);
  assert.match(api, /if \(!completed\)/);
  assert.match(api, /doğrulanmış bir sonuç üretmeden kesildi/);
});

test("yeni sohbet yalnız istemci durumunu sıfırlar", async () => {
  const chatbot = await source("app/chatbot/page.tsx");

  assert.match(chatbot, /Yeni sohbet/);
  assert.match(chatbot, /aria-label="Yeni sohbet başlat"/);
  assert.match(chatbot, /activeController\.current\?\.abort\(\)/);
  assert.match(chatbot, /messageInput\.current\?\.focus\(\)/);
  assert.doesNotMatch(chatbot, /\/api\/reset/);
});

test("chatbot arayüzü sağlayıcı veya model adı göstermez", async () => {
  const [chatbot, quality] = await Promise.all([
    source("app/chatbot/page.tsx"),
    source("app/quality/page.tsx"),
  ]);

  assert.doesNotMatch(chatbot, /Gemma|EVREN/i);
  assert.doesNotMatch(quality, /Gemma|EVREN|llm-(?:fast|large)/i);
  assert.match(chatbot, /Kanıta bağlı üretim/);
});

test("kalite sayfası doğrulanmış bağlam ve gözlem tarihini açıklar", async () => {
  const quality = await source("app/quality/page.tsx");

  assert.match(quality, /Doğrulanmış bağlam varlıkları/);
  assert.match(quality, /Kart adı/);
  assert.match(quality, /temporal_observation_count/);
  assert.match(quality, /yalnız kaynakta görülme kanıtı/);
});

test("grafik ve görselleştirme bileşenleri entegre edilmiştir", async () => {
  const [home, campaigns, compare] = await Promise.all([
    source("app/page.tsx"),
    source("app/campaigns/page.tsx"),
    source("app/compare/page.tsx"),
  ]);

  assert.match(home, /CampaignDistributionChart/);
  assert.match(home, /BankLogo/);
  assert.match(campaigns, /CampaignExplorer/);
  assert.match(compare, /ProfitRateChart/);
  assert.match(compare, /TermChart/);
  assert.match(compare, /CostChart/);
});

test("klavye, canlı bölge, erişilebilirlik ve responsive kuralları görünürdür", async () => {
  const [chatbot, globals, navbar] = await Promise.all([
    source("app/chatbot/page.tsx"),
    source("app/globals.css"),
    source("components/Navbar.module.css"),
  ]);

  assert.match(chatbot, /role="log"/);
  assert.match(chatbot, /aria-live="polite"/);
  assert.match(chatbot, /htmlFor="chat-message"/);
  assert.match(chatbot, /id="chat-message"/);
  assert.match(globals, /:focus-visible/);
  assert.match(navbar, /:focus-visible/);
  assert.match(navbar, /@media \(prefers-reduced-motion: reduce\)/);
});

test("özgün serif ve sans font entegrasyonu tanımlıdır", async () => {
  const [layout, globals] = await Promise.all([
    source("app/layout.tsx"),
    source("app/globals.css"),
  ]);

  assert.match(layout, /Playfair_Display/);
  assert.match(layout, /Geist/);
  assert.match(layout, /--font-playfair/);
  assert.match(layout, /--font-geist-sans/);
  assert.match(globals, /--font-serif:\s*var\(--font-playfair\)/);
  assert.match(globals, /--font-sans:\s*var\(--font-geist-sans\)/);
});

test("hero, pusula, yörünge ve floating AI animasyonları tanımlıdır", async () => {
  const [homeStyles, navbarStyles, floatingStyles] = await Promise.all([
    source("app/page.module.css"),
    source("components/Navbar.module.css"),
    source("components/FloatingAiLink.module.css"),
  ]);

  // Hero ve yörünge animasyonları
  assert.match(homeStyles, /@keyframes chevronGleam/);
  assert.match(homeStyles, /@keyframes needleCompassDrift/);
  assert.match(homeStyles, /@keyframes needlePointerShine/);
  assert.match(homeStyles, /@keyframes orbitFloat/);
  assert.match(homeStyles, /@keyframes bankOrbitFloat1/);
  assert.match(homeStyles, /@keyframes starCenterPulse/);
  assert.match(homeStyles, /pointer-events:\s*auto/);

  // Navbar pusula animasyonları
  assert.match(navbarStyles, /@keyframes haloPulse/);
  assert.match(navbarStyles, /@keyframes compassOrbitSpin/);
  assert.match(navbarStyles, /@keyframes glintCompassDrift/);
  assert.match(navbarStyles, /@keyframes navbarLineTravel/);

  // Floating AI animasyonları
  assert.match(floatingStyles, /@keyframes orbit/);
  assert.match(floatingStyles, /@keyframes sparkle/);
  assert.match(floatingStyles, /@keyframes pulseGlow/);
});

test("chatbot yerel finansal cevap veya sahte geçmiş içermez", async () => {
  const chatbot = await source("app/chatbot/page.tsx");
  assert.doesNotMatch(chatbot, /INITIAL_EXCHANGES|FALLBACK_ANSWERS|getFallbackAnswer/);
  assert.doesNotMatch(chatbot, /%2,49|%2,69|120 aya varan/);
  assert.match(chatbot, /Bağlantı kurulamadı/);
});

test("chatbot güvenli düşünme özeti ve akış göstergesi sunar", async () => {
  const chatbot = await source("app/chatbot/page.tsx");
  assert.match(chatbot, /<details/);
  assert.doesNotMatch(chatbot, /Yanıt hazırlanıyor/);
  assert.match(chatbot, /Kanıtlar kontrol ediliyor/);
  assert.doesNotMatch(chatbot, /raw.*reasoning|chain.?of.?thought/i);
  assert.match(chatbot, /thinkingDots/);
  assert.match(chatbot, /Yanıt güvenlik kontrolünden geçmedi/);
});
