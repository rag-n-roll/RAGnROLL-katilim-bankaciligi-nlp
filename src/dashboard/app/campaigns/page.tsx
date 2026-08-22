import fs from "node:fs";
import path from "node:path";
import styles from "./page.module.css";
import BankLogo from "../../components/BankLogo";
import CampaignExplorer from "./CampaignExplorer";

const campaigns = [
  {
    bank: "Kuveyt Türk",
    initials: "KT",
    name: "Taşıt Finansmanı Özel Oran Kampanyası",
    type: "Finansman",
  },
  {
    bank: "Albaraka Türk",
    initials: "AT",
    name: "Davet Et Kazan Kampanyası",
    type: "Kart",
    selected: true,
  },
  {
    bank: "Türkiye Finans",
    initials: "TF",
    name: "Katılma Hesabı Hoş Geldin Kampanyası",
    type: "Yatırım",
  },
  {
    bank: "Vakıf Katılım",
    initials: "VK",
    name: "Otomobil Finansmanı Avantajlı Paket",
    type: "Finansman",
  },
  {
    bank: "Ziraat Katılım",
    initials: "ZK",
    name: "Esnek Hesap Açılış Kampanyası",
    type: "Yatırım",
  },
];

type ProcessedCampaign = {
  id: string;
  bank_name?: string;
  title?: string;
  summary?: string | null;
  clean_text?: string | null;
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

const campaignType = (value?: string | null) => {
  if (value === "card") return "Kart";
  if (value === "investment") return "Yatırım";
  return "Finansman";
};

const processedPath = path.join(process.cwd(), "..", "..", "data", "processed", "campaigns.json");
const processedData = JSON.parse(fs.readFileSync(processedPath, "utf8")) as { records: ProcessedCampaign[] };
const allCampaignRows = processedData.records.map((record) => {
  const structured = record.structured ?? {};
  const rate = structured.profit_share_rate;
  const term = structured.term_months;
  return {
    id: record.id,
    bank: canonicalBankName(record.bank_name),
    campaign: record.title || "Güncel Kampanya",
    text: record.summary || record.clean_text || "Bu kampanya için ayrıntılı metin bulunmuyor.",
    summary: record.summary || "Bu kampanya için kısa özet bulunmuyor.",
    cleanText: record.clean_text || "Bu kampanya için temizlenmiş tam metin bulunmuyor.",
    type: campaignType(structured.product_type),
    rate: rate ? `%${String(rate).replace(".", ",")}` : "—",
    term: term ? `${term} Ay` : "—",
    cost: structured.fee_information || "—",
    validity: [record.start_date, record.end_date].filter(Boolean).join(" – ") || "Güncel",
  };
});
const totalCampaignCount = allCampaignRows.length;

function getTypeClass(type: string) {
  if (type === "Kart") return styles.cardBadge;
  if (type === "Yatırım") return styles.investmentBadge;

  return styles.financeBadge;
}

export default function CampaignsPage() {
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
          <span className={styles.waveOne}></span>
          <span className={styles.waveTwo}></span>
          <span className={styles.waveThree}></span>
        </div>
      </section>

      <CampaignExplorer rows={allCampaignRows} />
      {/* Legacy static workspace removed; CampaignExplorer owns selection state. */}
      {false && <section className={styles.campaignWorkspace}>
        {/* SOL KART */}
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Banka Bazlı Tüm Kampanyalar</h2>

            <span className={styles.campaignCount}>{totalCampaignCount} kampanya</span>
          </div>

          <div className={styles.campaignList}>
            {campaigns.map((campaign) => (
              <div
                key={campaign.bank}
                className={`${styles.campaignRow} ${
                  campaign.selected ? styles.selectedCampaign : ""
                }`}
              >
                <BankLogo bank={campaign.bank} size={34} />

                <div className={styles.campaignInfo}>
                  <strong>{campaign.bank}</strong>
                  <span>{campaign.name}</span>
                </div>

                <span
                  className={`${styles.typeBadge} ${getTypeClass(
                    campaign.type
                  )}`}
                >
                  {campaign.type}
                </span>
              </div>
            ))}
          </div>

          <a className={styles.viewAllButton} href="#all-campaigns">
            Tümünü Görüntüle <span>›</span>
          </a>
        </article>

        {/* ORTA KART */}
        <article className={styles.panel}>
          <div className={styles.contentTitle}>
            <span className={styles.titleIcon}>▤</span>
            <h2>Kampanya Metni</h2>
          </div>

          <div className={styles.campaignText}>
            <p>
              Albaraka Türk müşterilerini Albaraka Mobil uygulaması üzerinden
              “Davet Et Kazan” kampanyasına davet ediyoruz.
            </p>

            <p>
              Kampanya kapsamında, Albaraka Mobil’i ilk kez indiren ve davet
              kodunuzu kullanarak müşteri olan her arkadaşınız için 100 TL
              değerinde hediye puan kazanırsınız. Arkadaşınızın ilk harcaması
              sonrasında puanınız hesabınıza yüklenir.
            </p>

            <p>
              Kampanyadan yararlanmak için Albaraka Mobil uygulamasında yer alan
              kampanya sayfasından davet kodunuzu paylaşmanız yeterlidir.
            </p>

            <p>
              Kampanya 19 Mayıs 2024 – 30 Haziran 2024 tarihleri arasında
              geçerlidir.
            </p>

            <p>
              Detaylı bilgi için uygulamamızdaki kampanya sayfasını ziyaret
              ediniz.
            </p>
          </div>

          <div className={styles.aiNotice}>
            <span>ⓘ</span>
            Bu metin yapay zeka ile analiz edilerek finansal bilgiler
            çıkarılmıştır.
          </div>
        </article>

        {/* SAĞ KART */}
        <article className={styles.panel}>
          <div className={styles.contentTitle}>
            <span className={styles.titleIcon}>✣</span>
            <h2>Çıkarılan Bilgiler</h2>
          </div>

          <div className={styles.extractedList}>
            <div className={styles.extractedRow}>
              <span className={styles.extractedLabel}>🏦 Banka</span>
              <strong>Albaraka Türk</strong>
            </div>

            <div className={styles.extractedRow}>
              <span className={styles.extractedLabel}>▣ Ürün Türü</span>
              <span
                className={`${styles.typeBadge} ${styles.cardBadge}`}
              >
                Kart
              </span>
            </div>

            <div className={styles.extractedRow}>
              <span className={styles.extractedLabel}>% Kâr Payı</span>
              <strong>%2,69</strong>
            </div>

            <div className={styles.extractedRow}>
              <span className={styles.extractedLabel}>▣ Vade</span>
              <strong>36 Ay</strong>
            </div>

            <div className={styles.extractedRow}>
              <span className={styles.extractedLabel}>◉ Masraf</span>
              <strong>0 TL</strong>
            </div>

            <div className={styles.extractedRow}>
              <span className={styles.extractedLabel}>♙ Başvuru Koşulu</span>
              <strong>Albaraka Mobil üzerinden ilk kez müşteri olanlar</strong>
            </div>

            <div className={styles.extractedRow}>
              <span className={styles.extractedLabel}>▣ Geçerlilik Tarihi</span>
              <strong>19 Mayıs 2024 – 30 Haziran 2024</strong>
            </div>
          </div>
        </article>
      </section>}

      {false && <section className={styles.tableCard} id="all-campaigns">
        <h2>Tüm Kampanyalar <span className={styles.campaignCount}>{totalCampaignCount} kayıt</span></h2>

        <div className={styles.tableWrapper}>
          <table className={styles.dataTable}>
            <thead>
              <tr>
                <th>Banka</th>
                <th>Kampanya Adı</th>
                <th>Tür</th>
                <th>Kâr Payı</th>
                <th>Vade</th>
                <th>Masraf</th>
                <th>Geçerlilik</th>
              </tr>
            </thead>

            <tbody>
              {allCampaignRows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <div className={styles.tableBank}>
                      <BankLogo bank={row.bank} size={30} />

                      <strong>{row.bank}</strong>
                    </div>
                  </td>

                  <td className={styles.campaignCell}>
                    <details className={styles.campaignDisclosure}>
                      <summary>{row.campaign}<span>Metni aç</span></summary>
                      <div>{row.text}</div>
                    </details>
                  </td>

                  <td>
                    <span
                      className={`${styles.typeBadge} ${getTypeClass(row.type)}`}
                    >
                      {row.type}
                    </span>
                  </td>

                  <td>
                    <strong>{row.rate}</strong>

                  </td>

                  <td>{row.term}</td>
                  <td>{row.cost}</td>
                  <td>{row.validity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>}
    </main>
  );
}
