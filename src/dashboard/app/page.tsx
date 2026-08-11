import Link from "next/link";
import styles from "./page.module.css";
import CampaignDistributionChart from "../components/CampaignDistributionChart";

export default function HomePage() {
  return (
    <main className={styles.main}>
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <h1 className={styles.heroTitle}>
            Katılım bankacılığı
            <br />
            kampanyalarını tek ekranda
            <br />
            analiz edin.
          </h1>

          <p className={styles.heroDescription}>
            Finansman, kart ve yatırım kampanyalarını yapay zekâ desteğiyle
            karşılaştırın, en uygun fırsatları kolayca keşfedin.
          </p>

          <div className={styles.heroActions}>
            <Link href="/campaigns" className={styles.primaryButton}>
              <span className={styles.buttonIcon}>⌕</span>
              Kampanyaları Keşfet
            </Link>

            <Link href="/chatbot" className={styles.secondaryButton}>
              <span className={styles.aiIcon}>✦</span>
              AI Asistana Sor
            </Link>
          </div>
        </div>

        <div className={styles.heroVisual}>
          <div className={styles.visualCard}>
            <div className={styles.chartBars}>
              <span className={styles.barSmall}></span>
              <span className={styles.barMedium}></span>
              <span className={styles.barLarge}></span>
              <span className={styles.barMedium}></span>
              <span className={styles.barTall}></span>
            </div>

            <div className={styles.visualText}>
              <span className={styles.visualIcon}>✦</span>
              <strong>AI Analiz</strong>
              <small>Finansal veriler analiz ediliyor</small>
            </div>
          </div>
        </div>
      </section>
            <section className={styles.overviewGrid}>
        <div className={styles.summaryCards}>
          <article className={styles.summaryCard}>
            <div className={`${styles.summaryIcon} ${styles.bankIcon}`}>
              🏛
            </div>

            <div className={styles.summaryContent}>
              <span className={styles.summaryLabel}>Toplam Banka</span>
              <strong className={styles.bankValue}>6</strong>
            </div>
          </article>

          <article className={styles.summaryCard}>
            <div className={`${styles.summaryIcon} ${styles.campaignIcon}`}>
              🎁
            </div>

            <div className={styles.summaryContent}>
              <span className={styles.summaryLabel}>Toplam Kampanya</span>
              <strong className={styles.campaignValue}>128</strong>
            </div>
          </article>

          <article className={styles.summaryCard}>
            <div className={`${styles.summaryIcon} ${styles.profitIcon}`}>
              %
            </div>

            <div className={styles.summaryContent}>
              <span className={styles.summaryLabel}>Ortalama Kâr Payı</span>
              <strong className={styles.profitValue}>%18,4</strong>
            </div>
          </article>
        </div>
              <div className={styles.distributionCard}>
        <h2 className={styles.distributionTitle}>
          Bankalara Göre Kampanya Dağılımı
        </h2>

        <div className={styles.distributionContent}>
          <div className={styles.chartArea}>
            <CampaignDistributionChart />
          </div>

          <div className={styles.bankLegend}>
            <div className={styles.legendRow}>
              <span className={`${styles.legendDot} ${styles.dotPetrol}`}></span>
              <span className={styles.bankName}>Kuveyt Türk</span>
              <strong>52</strong>
              <span>%40</span>
            </div>

            <div className={styles.legendRow}>
              <span className={`${styles.legendDot} ${styles.dotTurquoise}`}></span>
              <span className={styles.bankName}>Albaraka Türk</span>
              <strong>34</strong>
              <span>%27</span>
            </div>

            <div className={styles.legendRow}>
              <span className={`${styles.legendDot} ${styles.dotYellow}`}></span>
              <span className={styles.bankName}>Türkiye Finans</span>
              <strong>24</strong>
              <span>%19</span>
            </div>

            <div className={styles.legendRow}>
              <span className={`${styles.legendDot} ${styles.dotTeal}`}></span>
              <span className={styles.bankName}>Vakıf Katılım</span>
              <strong>11</strong>
              <span>%9</span>
            </div>

            <div className={styles.legendRow}>
              <span className={`${styles.legendDot} ${styles.dotLight}`}></span>
              <span className={styles.bankName}>Ziraat Katılım</span>
              <strong>7</strong>
              <span>%5</span>
            </div>
          </div>
        </div>
      </div>
      </section>
   <section className={styles.campaignsSection}>
  <div className={styles.campaignsCard}>
    <h2 className={styles.campaignsTitle}>Güncel Kampanyalar</h2>

    <div className={styles.tableWrapper}>
      <table className={styles.campaignsTable}>
        <thead>
          <tr>
            <th>Banka</th>
            <th>Kampanya Adı</th>
            <th>Tür</th>
            <th>Tarih</th>
          </tr>
        </thead>

        <tbody>
          <tr>
            <td>
              <div className={styles.bankCell}>
                <span className={styles.bankLogo}>KT</span>
                <strong>Kuveyt Türk</strong>
              </div>
            </td>

            <td>Taşıt Finansmanı Özel Oran Kampanyası</td>

            <td>
              <span className={`${styles.typeBadge} ${styles.financeBadge}`}>
                Finansman
              </span>
            </td>

            <td>20 Mayıs 2024</td>
          </tr>

          <tr>
            <td>
              <div className={styles.bankCell}>
                <span className={styles.bankLogo}>AT</span>
                <strong>Albaraka Türk</strong>
              </div>
            </td>

            <td>Davet Et Kazan Kampanyası</td>

            <td>
              <span className={`${styles.typeBadge} ${styles.cardBadge}`}>
                Kart
              </span>
            </td>

            <td>19 Mayıs 2024</td>
          </tr>

          <tr>
            <td>
              <div className={styles.bankCell}>
                <span className={styles.bankLogo}>TF</span>
                <strong>Türkiye Finans</strong>
              </div>
            </td>

            <td>Katılma Hesabı Hoş Geldin Kampanyası</td>

            <td>
              <span className={`${styles.typeBadge} ${styles.investmentBadge}`}>
                Yatırım
              </span>
            </td>

            <td>18 Mayıs 2024</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</section>
    </main>
  );
}