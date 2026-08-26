import assert from "node:assert/strict";
import test from "node:test";
import {
  cleanCampaignText,
  parseCampaignText,
} from "../app/campaigns/textFormatter.ts";

test("web scraping kaynaklı kırık satırları ve cümle ortası satır sonlarını birleştirir", () => {
  const rawScraped = `Ziraat Katılım Bankkart kredi kartınız ile
Yolcu360
'tan yapacağınız
yurt dışı araç kiralama
işlemlerinde, Bankkart müşterilerimize özel
BK360YD
kodu ile liste fiyatları (üstü kırmızı çizgili fiyatlar) üzerinden
%15 indirim
uygulanacaktır.`;

  const blocks = parseCampaignText(rawScraped);
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].type, "paragraph");
  assert.equal(
    blocks[0].text,
    "Ziraat Katılım Bankkart kredi kartınız ile Yolcu360'tan yapacağınız yurt dışı araç kiralama işlemlerinde, Bankkart müşterilerimize özel BK360YD kodu ile liste fiyatları (üstü kırmızı çizgili fiyatlar) üzerinden %15 indirim uygulanacaktır."
  );
});

test("sayı, para birimi ve ek ayrılmalarını temizler", () => {
  const raw = `Yaptırdığınız her BES ve Erken BES için
500 TL,
toplamda maksimum
2.000
TL
’ye varan Worldpuan kazanın.`;

  const blocks = parseCampaignText(raw);
  assert.equal(blocks.length, 1);
  assert.equal(
    blocks[0].text,
    "Yaptırdığınız her BES ve Erken BES için 500 TL, toplamda maksimum 2.000 TL’ye varan Worldpuan kazanın."
  );
});

test("tarih aralıkları ve tireli satırları birleştirir", () => {
  const raw = `Kampanya Dönemi
01-04-2025
-
31-12-2026`;

  const blocks = parseCampaignText(raw);
  assert.equal(blocks.length, 2);
  assert.equal(blocks[0].type, "heading");
  assert.equal(blocks[0].text, "Kampanya Dönemi");
  assert.equal(blocks[1].type, "paragraph");
  assert.equal(blocks[1].text, "01-04-2025 - 31-12-2026");
});

test("başlık, soru ve liste maddelerini doğru tespit edip yapılandırır", () => {
  const raw = `Kampanyaya Nasıl Katılırım?
Kampanyaya katılmak için “MARKET” yazıp 6026’ya SMS gönderilmesi gerekmektedir.
Kampanya Koşulları:
• Kampanya 1-31 Ağustos 2026 tarihleri arasında geçerlidir.
• Kampanya müşteri bazlıdır.
1. İlk aşamayı tamamlayın.
2. İkinci aşamayı tamamlayın.`;

  const blocks = parseCampaignText(raw);
  assert.equal(blocks.length, 5);

  assert.equal(blocks[0].type, "heading");
  assert.equal(blocks[0].text, "Kampanyaya Nasıl Katılırım?");

  assert.equal(blocks[1].type, "paragraph");
  assert.equal(
    blocks[1].text,
    "Kampanyaya katılmak için “MARKET” yazıp 6026’ya SMS gönderilmesi gerekmektedir."
  );

  assert.equal(blocks[2].type, "heading");
  assert.equal(blocks[2].text, "Kampanya Koşulları:");

  assert.equal(blocks[3].type, "list");
  assert.equal(blocks[3].ordered, false);
  assert.equal(blocks[3].items.length, 2);
  assert.equal(
    blocks[3].items[0],
    "Kampanya 1-31 Ağustos 2026 tarihleri arasında geçerlidir."
  );
  assert.equal(blocks[3].items[1], "Kampanya müşteri bazlıdır.");

  assert.equal(blocks[4].type, "list");
  assert.equal(blocks[4].ordered, true);
  assert.equal(blocks[4].items.length, 2);
  assert.equal(blocks[4].items[0], "İlk aşamayı tamamlayın.");
  assert.equal(blocks[4].items[1], "İkinci aşamayı tamamlayın.");
});

test("cleanCampaignText düz metin olarak akıcı ve temiz çıktı üretir", () => {
  const raw = `Kampanya Detayları:
Albaraka Mobil’e giriş yapın,
Kampanyalar bölümünden
“Albaraka ile Geleceğim Güvende!”
kampanyasına katılın.`;

  const cleaned = cleanCampaignText(raw);
  assert.equal(
    cleaned,
    "Kampanya Detayları:\n\nAlbaraka Mobil’e giriş yapın, Kampanyalar bölümünden “Albaraka ile Geleceğim Güvende!” kampanyasına katılın."
  );
});

test("boş veya tanımsız girdileri güvenle karşılar", () => {
  assert.deepEqual(parseCampaignText(null), []);
  assert.deepEqual(parseCampaignText(""), []);
  assert.deepEqual(parseCampaignText("   "), []);
  assert.equal(cleanCampaignText(null), "");
  assert.equal(cleanCampaignText(""), "");
});
