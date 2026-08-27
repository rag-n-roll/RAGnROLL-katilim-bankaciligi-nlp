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

const displayFeeInformation = (value?: string | null) => {
  if (value?.toLocaleLowerCase("tr-TR") === "masrafsız") return "Masrafsız";
  return value || "—";
};

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
            cost: displayFeeInformation(structured.fee_information),
            validity: [record.start_date, record.end_date].filter(Boolean).join(" – ") || "Güncel",
          };
        });
      }
    }
  } catch {
    // Doğrulanmamış statik kampanya üretme; görünür boş durum gösterilir.
  }
  return [];
}

export default async function CampaignsPage() {
  let rows: CampaignRowItem[] = [];

  try {
    // API'nin üst sınırıyla tüm katalog tek istekte alınır; istemci tarafı
    // filtreleri yalnızca ilk 100 kayıtla sınırlı kalmaz.
    const apiResult = await getCampaigns({ limit: 500 });
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
          cost: displayFeeInformation(fee),
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
