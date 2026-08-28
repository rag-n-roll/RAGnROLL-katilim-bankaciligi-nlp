import Link from "next/link";
import { connection } from "next/server";
import CampaignDistributionChart from "../components/CampaignDistributionChart";
import BankLogo from "../components/BankLogo";
import styles from "./page.module.css";
import { getCampaigns, getDashboardSnapshot } from "../services/api";
import { sampleCampaigns } from "./campaigns/campaignSelection";
import { mapCampaignType } from "./campaigns/campaignType";

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

export default async function HomePage() {
  // Rastgele seçim build sırasında sabitlenmez; her istekte yeniden yapılır.
  await connection();
  const [snapshotResult, campaignsResult] = await Promise.allSettled([
    getDashboardSnapshot(),
    getCampaigns({ limit: 500 }),
  ]);
  const snapshot = snapshotResult.status === "fulfilled" ? snapshotResult.value : null;
  const campaignPool = campaignsResult.status === "fulfilled"
    ? campaignsResult.value.items.map((campaign) => ({
        id: campaign.id,
        bank_name: campaign.bank_name,
        title: campaign.title,
        product_type: typeof campaign.structured?.product_type === "string"
          ? campaign.structured.product_type : null,
        updated_at: campaign.scraped_at,
      }))
    : snapshot?.recent_campaigns ?? [];
  const bankCount = snapshot?.summary?.bank_count ?? "—";
  const campaignCount = snapshot?.summary?.campaign_count ?? "—";
  const avgProfitRate = snapshot?.summary?.average_profit_share_rate
    ? `%${snapshot.summary.average_profit_share_rate.toFixed(1).replace(".", ",")}`
    : "—";

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
    : [];

  const legendRows = hasValidDistributions
    ? snapshot!.distributions.banks.map((b) => [
        b.name,
        String(b.campaign_count),
        `%${(b.campaign_share * 100).toFixed(1).replace(".", ",")}`,
      ] as [string, string, string])
    : [];

  const displayCampaigns = sampleCampaigns(campaignPool).map((c) => ({
        id: c.id,
        bank: c.bank_name,
        title: c.title,
        type: mapCampaignType(c.product_type),
        date: c.updated_at
          ? new Date(c.updated_at).toLocaleDateString("tr-TR", {
              day: "numeric",
              month: "long",
              year: "numeric",
            })
          : "Güncel",
      }));

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
                  {hasValidDistributions ? (
                    <CampaignDistributionChart
                      items={distributionItems}
                      total={
                        typeof campaignCount === "number"
                          ? campaignCount
                          : undefined
                      }
                    />
                  ) : (
                    <p className={styles.emptyData} role="status">
                      Doğrulanmış güncel veri alınamadı.
                    </p>
                  )}
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
          {displayCampaigns.length === 0 ? (
            <p className={styles.emptyData} role="status">
              Doğrulanmış güncel veri alınamadı.
            </p>
          ) : displayCampaigns.map((campaign) => (
            <Link
              href={`/campaigns?campaign=${encodeURIComponent(campaign.id)}`}
              prefetch={false}
              className={styles.campaignRow}
              key={campaign.id}
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
