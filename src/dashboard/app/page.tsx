import Link from "next/link";
import CampaignDistributionChart from "../components/CampaignDistributionChart";
import BankLogo from "../components/BankLogo";
import styles from "./page.module.css";
import { getDashboardSnapshot } from "../services/api";
import type { DashboardSnapshotData } from "../services/api";


const FALLBACK_CAMPAIGNS = [
  { initials: "KT", bank: "Kuveyt Türk", title: "Taşıt Finansmanı Özel Oran Kampanyası", type: "Finansman", date: "20 Mayıs 2024" },
  { initials: "AT", bank: "Albaraka Türk", title: "Davet Et Kazan Kampanyası", type: "Kart", date: "19 Mayıs 2024" },
  { initials: "TF", bank: "Türkiye Finans", title: "Katılma Hesabı Hoş Geldin Kampanyası", type: "Yatırım", date: "18 Mayıs 2024" },
  { initials: "VK", bank: "Vakıf Katılım", title: "Avantajlı Konut Finansmanı Kampanyası", type: "Finansman", date: "17 Mayıs 2024" },
  { initials: "ZK", bank: "Ziraat Katılım", title: "Bankkart Alışverişe Ekstra Kazanç", type: "Kart", date: "16 Mayıs 2024" },
  { initials: "EK", bank: "Emlak Katılım", title: "Yeni Müşterilere Özel Katılma Hesabı", type: "Yatırım", date: "15 Mayıs 2024" },
  { initials: "HF", bank: "Hayat Finans", title: "Dijital Finansman Fırsatları", type: "Finansman", date: "14 Mayıs 2024" },
  { initials: "TK", bank: "TOM Katılım", title: "Kart Harcamalarına Özel Nakit İade", type: "Kart", date: "13 Mayıs 2024" },
];

const FALLBACK_LEGEND: Array<[string, string, string]> = [
  ["Kuveyt Türk", "69", "%14,6"],
  ["Albaraka Türk", "48", "%10,2"],
  ["Türkiye Finans", "13", "%2,8"],
  ["Vakıf Katılım", "3", "%0,6"],
  ["Ziraat Katılım", "208", "%44,2"],
  ["Emlak Katılım", "64", "%13,6"],
  ["Hayat Finans", "10", "%2,1"],
  ["TOM Katılım", "10", "%2,1"],
  ["Dünya Katılım", "45", "%9,6"],
  ["Adil Katılım", "1", "%0,2"],
];

const heroBanks = [
  { bank: "Kuveyt Türk", size: 54 },
  { bank: "Hayat Finans", size: 34 },
  { bank: "Albaraka Türk", size: 54 },
  { bank: "TOM Katılım", size: 34 },
  { bank: "Türkiye Finans", size: 54 },
  { bank: "Dünya Katılım", size: 34 },
  { bank: "Vakıf Katılım", size: 54 },
  { bank: "Adil Katılım", size: 34 },
  { bank: "Ziraat Katılım", size: 54 },
  { bank: "Emlak Katılım", size: 34 },
];

function mapProductType(type?: string | null): string {
  if (!type) return "Finansman";
  const lower = type.toLowerCase();
  if (lower.includes("card") || lower.includes("kart")) return "Kart";
  if (lower.includes("invest") || lower.includes("katıl") || lower.includes("yatırım")) return "Yatırım";
  return "Finansman";
}

export default async function HomePage() {
  let snapshot: DashboardSnapshotData | null = null;

  try {
    snapshot = await getDashboardSnapshot();
  } catch {
    // Backend bağlı değilse veya hata verirse güvenli fallback
    snapshot = null;
  }
  const bankCount = snapshot?.summary?.bank_count || 10;
  const campaignCount = snapshot?.summary?.campaign_count || 471;
  const avgProfitRate = snapshot?.summary?.average_profit_share_rate
    ? `%${snapshot.summary.average_profit_share_rate.toFixed(1).replace(".", ",")}`
    : "%18,4";

  const hasValidDistributions = Boolean(
    snapshot?.distributions?.banks &&
      snapshot.distributions.banks.length > 0 &&
      snapshot.distributions.banks.some((b) => b.campaign_count > 0)
  );

  const distributionItems = hasValidDistributions
    ? snapshot!.distributions.banks.map((b) => ({
        name: b.name,
        count: b.campaign_count,
      }))
    : undefined;

  const legendRows = hasValidDistributions
    ? snapshot!.distributions.banks.map((b) => [
        b.name,
        String(b.campaign_count),
        `%${(b.campaign_share * 100).toFixed(1).replace(".", ",")}`,
      ] as [string, string, string])
    : FALLBACK_LEGEND;

  const displayCampaigns = snapshot?.recent_campaigns?.length
    ? snapshot.recent_campaigns.map((c) => ({
        bank: c.bank_name,
        title: c.title,
        type: mapProductType(c.product_type),
        date: c.updated_at
          ? new Date(c.updated_at).toLocaleDateString("tr-TR", {
              day: "numeric",
              month: "long",
              year: "numeric",
            })
          : "Güncel",
      }))
    : FALLBACK_CAMPAIGNS;

  return (
    <main className={styles.main}>
      <section className={styles.hero}>
        <div className={styles.heroPattern} aria-hidden="true" />
        <div className={styles.splitChevron} aria-hidden="true" />
        <div className={`${styles.diagonalDivider} ${styles.dividerOne}`} aria-hidden="true" />
        <div className={`${styles.diagonalDivider} ${styles.dividerTwo}`} aria-hidden="true" />
        <div className={styles.heroZoneGrid}>
          <div className={styles.heroStarDivider} aria-hidden="true">
            <i>✦</i>
            <b>✦</b>
            <span>✦</span>
          </div>
          <div className={styles.heroLeft}>
            <h1>
              <span className={styles.heroTitleIntro}>
                <b>Katılım bankacılığında</b>
                <b>fırsatları</b>
              </span>
              <strong>
                <em>TEK MERKEZDEN</em>
                <span>keşfedin.</span>
              </strong>
            </h1>
            <ul className={styles.heroBenefits}>
              <li>Kampanyaları tek ekranda görün</li>
              <li>Bankaları saniyeler içinde karşılaştırın</li>
              <li>Kâr payı, vade ve avantajları analiz edin</li>
              <li>Pusula AI ile en uygun seçeneği bulun</li>
            </ul>
            <div className={styles.heroRightActions}>
              <Link href="/campaigns">
                Kampanyaları İncele <span>→</span>
              </Link>
              <Link href="/chatbot">
                <i>✦</i> AI Asistana Sor
              </Link>
            </div>
          </div>

          <div
            className={styles.heroBankOrbit}
            aria-label="Analiz edilen katılım bankaları"
          >
            <div className={styles.centerNeedle} aria-hidden="true">
              <b>N</b>
              <span />
            </div>
            {heroBanks.map(({ bank, size }, index) => (
              <span
                className={styles[`orbitBank${index + 1}`]}
                key={bank}
                title={bank}
              >
                <BankLogo bank={bank} size={size} />
              </span>
            ))}
          </div>
        </div>
      </section>

      <section
        className={styles.overviewSection}
        aria-label="Platform ve kampanya özeti"
      >
        <div className={styles.chartBlock}>
          <div className={styles.blockHeading}>
            <div>
              <h3>Kampanya dağılımı</h3>
              <p>Bankalara göre aktif kampanyalar</p>
            </div>
            <span>Son 30 gün</span>
          </div>
          <div className={styles.chartContent}>
            <div className={styles.chartVisualColumn}>
              <div className={styles.chartArea}>
                <CampaignDistributionChart
                  items={distributionItems}
                  total={campaignCount}
                />
              </div>
              <div className={styles.overviewMetrics}>
                <div className={styles.metricGrid}>
                  <div>
                    <strong>{bankCount}</strong>
                    <span>Analiz edilen banka</span>
                  </div>
                  <div>
                    <strong>{campaignCount}</strong>
                    <span>Güncel kampanya</span>
                  </div>
                  <div>
                    <strong>{avgProfitRate}</strong>
                    <span>Ortalama kâr payı</span>
                  </div>
                </div>
                <p className={styles.updateNote}>
                  <span>✦</span> Veriler düzenli olarak güncellenir ve Pusula AI
                  tarafından yapılandırılır.
                </p>
              </div>
            </div>
            <div className={styles.legend}>
              {legendRows.map(([bank, count, percent]) => (
                <div className={styles.legendRow} key={bank}>
                  <BankLogo bank={bank} size={40} />
                  <span>{bank}</span>
                  <strong>{count}</strong>
                  <small>{percent}</small>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className={styles.campaignSection}>
        <div className={styles.campaignHeading}>
          <div>
            <span className={styles.sectionLabel}>YENİ FIRSATLAR</span>
            <h2>Güncel kampanyalar</h2>
            <p>Katılım bankalarının yeni ve öne çıkan kampanyaları.</p>
          </div>
          <Link href="/campaigns">
            Tümünü gör <span>→</span>
          </Link>
        </div>
        <div className={styles.campaignList}>
          {displayCampaigns.map((campaign) => (
            <Link
              href="/campaigns"
              className={styles.campaignRow}
              key={campaign.title}
            >
              <BankLogo bank={campaign.bank} size={36} />
              <strong>{campaign.bank}</strong>
              <h3>{campaign.title}</h3>
              <span
                className={`${styles.typeBadge} ${
                  styles[campaign.type.toLowerCase()] ?? styles.finansman
                }`}
              >
                {campaign.type}
              </span>
              <time>{campaign.date}</time>
              <i>→</i>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
