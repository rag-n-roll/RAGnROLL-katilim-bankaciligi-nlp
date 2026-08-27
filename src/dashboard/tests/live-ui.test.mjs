import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const dashboardRoot = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, dashboardRoot), "utf8");
}

test("geliştirme sunucusu 127.0.0.1 istemcisini hydrate eder", async () => {
  const nextConfig = await source("next.config.ts");

  assert.match(nextConfig, /allowedDevOrigins:\s*\[\s*["']127\.0\.0\.1["']\s*\]/);
});

test("financing api istemcisi kaynaklı kampanya ve teklif sözleşmesini taşır", async () => {
  const api = await source("services/api.ts");

  assert.match(api, /export function getFinancingCampaigns|export async function getFinancingCampaigns/);
  assert.match(api, /export function getFinancingQuotes|export async function getFinancingQuotes/);
  assert.match(api, /\/financing-campaigns\?catalog_only=true/);
  assert.match(api, /\/financing-quotes/);
  assert.match(api, /source_url\?: string \| null/);
  assert.match(api, /retrieved_at\?: string \| null/);
});

test("chat kaynak sözleşmesi PDF belge ve sayfa kaynağını kullanıcıya taşır", async () => {
  const [api, chatbot] = await Promise.all([
    source("services/api.ts"),
    source("app/chatbot/page.tsx"),
  ]);

  for (const field of ["document_id", "page_start", "page_end", "publisher"]) {
    assert.match(api, new RegExp(`${field}\\?:`));
  }
  assert.match(chatbot, /page_start/);
  assert.match(chatbot, /page_end/);
  assert.match(chatbot, /Kaynaklar:/);
  assert.doesNotMatch(chatbot, /Kaynak Kampanyalar:/);
});

test("karşılaştırma sayfası yalnız kaynaklı finansman tekliflerini kullanır", async () => {
  const compare = await source("app/compare/page.tsx");

  assert.doesNotMatch(compare, /BANK_RATE_BASE|DEFAULT_TABLE_ROWS/);
  assert.doesNotMatch(compare, /Fallback calculated rows|Backend offline: compute/);
  assert.doesNotMatch(compare, /compareCampaigns/);
  assert.match(compare, /getFinancingCampaigns/);
  assert.match(compare, /getFinancingQuotes/);
  assert.match(compare, /financingAmount/);
  assert.match(compare, /termMonths/);
  assert.match(compare, /feePriority/);
  assert.match(compare, /source_url/);
  assert.match(compare, /Doğrulanmış teklif bulunamadı/);
  assert.match(compare, /Resmî kaynak.*→/);
});

test("karşılaştırma grafikleri kaynak dışı varsayılan finansal değer üretmez", async () => {
  const charts = await source("components/ComparisonCharts.tsx");

  assert.doesNotMatch(charts, /DEFAULT_(BANKS|PROFIT_RATES|TERMS|COSTS)/);
  assert.doesNotMatch(charts, /\? i\.rate : 2\.5|\? i\.term : 24|\? i\.cost : 0/);
  assert.match(charts, /return null/);
});

test("mobil karşılaştırmada yüzen AI düğmesi ana eylemi kapatmaz", async () => {
  const styles = await source("app/compare/page.module.css");

  assert.match(
    styles,
    /\.main\s*\+\s*:global\(a\[aria-label\^=["']Pusula AI["']\]\)\s*\{[^}]*display:\s*none/s
  );
});

test("sayfalar canlı API sözleşmelerini korur", async () => {
  const [home, campaigns, compare, chatbot] = await Promise.all([
    source("app/page.tsx"),
    source("app/campaigns/page.tsx"),
    source("app/compare/page.tsx"),
    source("app/chatbot/page.tsx"),
  ]);

  assert.match(home, /getDashboardSnapshot/);
  assert.match(campaigns, /getCampaigns/);
  assert.match(compare, /getFinancingQuotes/);
  assert.match(chatbot, /streamChat/);
  for (const handler of ["onMeta", "onDelta", "onReplace", "onDone"]) {
    assert.match(chatbot, new RegExp(`${handler}:`));
  }
});

test("çıkarılan bilgiler yalnız doğrulanmış değerleri gösterir", async () => {
  const explorer = await source("app/campaigns/CampaignExplorer.tsx");

  assert.match(explorer, /\.filter\(\(\{ value \}\) => value\.trim\(\) !== "—"\)/);
  assert.match(explorer, /extractedDetails\.map/);
});

test("masrafsız bilgisi kullanıcıya büyük harfle gösterilir", async () => {
  const campaigns = await source("app/campaigns/page.tsx");

  assert.match(campaigns, /displayFeeInformation/);
  assert.match(campaigns, /return "Masrafsız"/);
});

test("chatbot karşılaştırma kriterlerini sonraki SSE isteğine taşır", async () => {
  const [chatbot, api] = await Promise.all([
    source("app/chatbot/page.tsx"),
    source("services/api.ts"),
  ]);

  assert.match(api, /export type ChatConversationState/);
  assert.match(api, /conversation_state:\s*conversationState/);
  assert.match(chatbot, /setConversationState\(meta\.conversation_state \?\? null\)/);
  assert.match(chatbot, /setConversationState\(null\)/);
  assert.match(chatbot, /conversationState,\s*controller\.signal/);
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
  assert.match(navbarStyles, /@keyframes compassReflectionSweep/);
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

test("ana sayfa backend yokken sahte finansal sayı veya kampanya üretmez", async () => {
  const home = await source("app/page.tsx");
  const campaigns = await source("app/campaigns/page.tsx");
  const distribution = await source("components/CampaignDistributionChart.tsx");

  assert.doesNotMatch(home, /FALLBACK_CAMPAIGNS|FALLBACK_LEGEND/);
  assert.doesNotMatch(home, /\|\|\s*471|%18,4/);
  assert.doesNotMatch(distribution, /DEFAULT_BANKS|DEFAULT_VALUES/);
  assert.doesNotMatch(campaigns, /FALLBACK_STATIC_ROWS|%2,49|20 Mayıs 2024/);
  assert.match(home, /Doğrulanmış güncel veri alınamadı/);
});

test("chatbot güvenli düşünme özeti ve akış göstergesi sunar", async () => {
  const chatbot = await source("app/chatbot/page.tsx");
  assert.match(chatbot, /<details/);
  assert.doesNotMatch(chatbot, /Yanıt hazırlanıyor/);
  assert.match(chatbot, /Kanıtlar kontrol ediliyor/);
  assert.doesNotMatch(chatbot, /raw.*reasoning|chain.?of.?thought/i);
  assert.match(chatbot, /thinkingDots/);
  assert.match(chatbot, /Doğrulanmış yanıt hazırlandı/);
  assert.match(chatbot, /Destek kapsamı bilgisi paylaşıldı/);
  assert.doesNotMatch(chatbot, /güvenlik kontrol|güvenli yanıt yönlendirmesi/i);
  assert.doesNotMatch(chatbot, /thinkingFailed/);
});
