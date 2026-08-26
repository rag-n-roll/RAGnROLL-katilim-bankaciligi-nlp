import fs from "node:fs";
import path from "node:path";
import styles from "./page.module.css";
import CampaignExplorer, { type CampaignRowItem } from "./CampaignExplorer";
import { getCampaigns } from "../../services/api";
import { cleanCampaignText } from "./textFormatter";

type ProcessedCampaign = {
  id: string;
  bank_name?: string;
  title?: string;
  summary?: string | null;
  clean_text?: string | null;
  content?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  structured?: {
    product_type?: string | null;
    profit_share_rate?: string | number | null;
    term_months?: string | number | null;
    fee_information?: string | null;
  };
};

const canonicalBankName = (name = "") => {
  const value = name.toLocaleLowerCase("tr-TR");
  if (value.includes("kuveyt")) return "Kuveyt Türk";
  if (value.includes("albaraka")) return "Albaraka Türk";
  if (value.includes("türkiye finans")) return "Türkiye Finans";
  if (value.includes("vakıf")) return "Vakıf Katılım";
  if (value.includes("ziraat")) return "Ziraat Katılım";
  if (value.includes("emlak")) return "Emlak Katılım";
  if (value.includes("hayat")) return "Hayat Finans";
  if (value.includes("tom")) return "TOM Katılım";
  if (value.includes("dünya")) return "Dünya Katılım";
  if (value.includes("adil")) return "Adil Katılım";
  return name || "Katılım Bankası";
};

const mapCampaignType = (value?: string | null) => {
  if (!value) return "Finansman";
  const lower = value.toLowerCase();
  if (lower.includes("card") || lower.includes("kart")) return "Kart";
  if (lower.includes("invest") || lower.includes("katıl") || lower.includes("yatırım")) return "Yatırım";
  return "Finansman";
};

const FALLBACK_STATIC_ROWS: CampaignRowItem[] = [
  {
    id: "kt-1",
    bank: "Kuveyt Türk",
    campaign: "Taşıt Finansmanı Özel Oran Kampanyası",
    text: "Kuveyt Türk taşıt finansmanında avantajlı kâr payı oranları ile yeni araç sahibi olun.",
    summary: "24 aya varan vadelerle avantajlı taşıt finansmanı imkânı.",
    cleanText: "Kuveyt Türk taşıt finansmanında avantajlı kâr payı oranları ile hayalinizdeki araca sahip olma fırsatı.",
    type: "Finansman",
    rate: "%2,49",
    term: "24 Ay",
    cost: "0 TL",
    validity: "20 Mayıs 2024 – 30 Haziran 2024",
  },
  {
    id: "at-1",
    bank: "Albaraka Türk",
    campaign: "Davet Et Kazan Kampanyası",
    text: "Albaraka Mobil üzerinden arkadaşını davet eden müşterilerimize özel hediye puanlar.",
    summary: "Arkadaşını davet et, harcama yaptıkça puan kazan.",
    cleanText: "Albaraka Türk müşterilerini Albaraka Mobil uygulaması üzerinden Davet Et Kazan kampanyasına davet ediyoruz.",
    type: "Kart",
    rate: "%2,69",
    term: "36 Ay",
    cost: "0 TL",
    validity: "19 Mayıs 2024 – 30 Haziran 2024",
  },
  {
    id: "tf-1",
    bank: "Türkiye Finans",
    campaign: "Katılma Hesabı Hoş Geldin Kampanyası",
    text: "Yeni açılan katılma hesaplarında yüksek getiri paylaşımı fırsatı.",
    summary: "Katılma hesaplarında ilk müşterilere özel kâr payı paylaşım oranları.",
    cleanText: "Türkiye Finans Katılma Hesabı Hoş Geldin Kampanyası ile birikimlerinizi güvenle değerlendirin.",
    type: "Yatırım",
    rate: "%2,79",
    term: "48 Ay",
    cost: "250 TL",
    validity: "18 Mayıs 2024 – 31 Temmuz 2024",
  },
  {
    id: "vk-1",
    bank: "Vakıf Katılım",
    campaign: "Avantajlı Konut Finansmanı Kampanyası",
    text: "Ev sahibi olmak isteyen müşterilere özel esnek ödeme planlı finansman.",
    summary: "Vakıf Katılım ile uygun kâr payı ve uzun vadeli konut finansmanı.",
    cleanText: "Avantajlı Konut Finansmanı Kampanyası kapsamında esnek geri ödeme seçenekleri sunulmaktadır.",
    type: "Finansman",
    rate: "%2,89",
    term: "36 Ay",
    cost: "250 TL",
    validity: "17 Mayıs 2024 – 31 Aralık 2024",
  },
  {
    id: "zk-1",
    bank: "Ziraat Katılım",
    campaign: "Bankkart Alışverişe Ekstra Kazanç",
    text: "Bankkart ile anlaşmalı üye işyerlerinde yapacağınız harcamalarda ekstra puan.",
    summary: "Ziraat Katılım Bankkart ile harcadıkça kazandıran kampanya.",
    cleanText: "Bankkart ile yapacağınız market ve akaryakıt alışverişlerinde ekstra puan kazanma fırsatı.",
    type: "Kart",
    rate: "%2,95",
    term: "24 Ay",
    cost: "150 TL",
    validity: "16 Mayıs 2024 – 15 Temmuz 2024",
  },
];

function loadLocalProcessedCampaigns(): CampaignRowItem[] {
  try {
    const candidatePath = path.resolve(process.cwd(), "..", "..", "data", "processed", "campaigns.json");
    if (fs.existsSync(/* turbopackIgnore: true */ candidatePath)) {
      const rawContent = fs.readFileSync(/* turbopackIgnore: true */ candidatePath, "utf8");
      const parsed = JSON.parse(rawContent) as { records?: ProcessedCampaign[] } | ProcessedCampaign[];
      const records = Array.isArray(parsed) ? parsed : parsed.records ?? [];
      if (records.length > 0) {
        return records.map((record) => {
          const structured = record.structured ?? {};
          const rate = structured.profit_share_rate;
          const term = structured.term_months;
          return {
            id: record.id,
            bank: canonicalBankName(record.bank_name),
            campaign: record.title || "Güncel Kampanya",
            text: cleanCampaignText(record.summary || record.clean_text || record.content) || "Bu kampanya için ayrıntılı metin bulunmuyor.",
            summary: cleanCampaignText(record.summary) || "Bu kampanya için kısa özet bulunmuyor.",
            cleanText: cleanCampaignText(record.clean_text || record.content || record.summary) || "Bu kampanya için temizlenmiş tam metin bulunmuyor.",
            type: mapCampaignType(structured.product_type),
            rate: rate ? `%${String(rate).replace(".", ",")}` : "—",
            term: term ? `${term} Ay` : "—",
            cost: structured.fee_information || "—",
            validity: [record.start_date, record.end_date].filter(Boolean).join(" – ") || "Güncel",
          };
        });
      }
    }
  } catch {
    // Dosya okunamadıysa fallback kullanılır
  }
  return FALLBACK_STATIC_ROWS;
}

export default async function CampaignsPage() {
  let rows: CampaignRowItem[] = [];

  try {
    const apiResult = await getCampaigns({ limit: 100 });
    if (apiResult && apiResult.items && apiResult.items.length > 0) {
      rows = apiResult.items.map((item) => {
        const structured = item.structured as Record<string, unknown> | undefined;
        const rate = structured?.profit_share_rate as number | string | undefined;
        const term = structured?.term_months as number | string | undefined;
        const fee = structured?.fee_information as string | undefined;
        return {
          id: item.id,
          bank: canonicalBankName(item.bank_name),
          campaign: item.title,
          text: cleanCampaignText(item.content) || "Kampanya ayrıntısı bulunmuyor.",
          summary: cleanCampaignText(item.title) || item.title,
          cleanText: cleanCampaignText(item.content) || "Tam metin bulunmuyor.",
          type: mapCampaignType((structured?.product_type as string) || null),
          rate: rate ? `%${String(rate).replace(".", ",")}` : "—",
          term: term ? `${term} Ay` : "—",
          cost: fee || "—",
          validity: "Güncel",
        };
      });
    }
  } catch {
    // API bağlantısı yoksa yerel veriye geçilir
  }

  if (rows.length === 0) {
    rows = loadLocalProcessedCampaigns();
  }

  return (
    <main className={styles.main}>
      <section className={styles.pageHeader}>
        <div>
          <h1 className={styles.title}>Kampanya Merkezi</h1>
          <p className={styles.description}>
            Bankaların güncel kampanyalarını, kampanya metinlerini ve çıkarılan
            finansal bilgileri tek ekranda inceleyin.
          </p>
        </div>

        <div className={styles.headerDecoration}>
          <span className={styles.waveOne} />
          <span className={styles.waveTwo} />
          <span className={styles.waveThree} />
        </div>
      </section>

      <CampaignExplorer rows={rows} />
    </main>
  );
}
