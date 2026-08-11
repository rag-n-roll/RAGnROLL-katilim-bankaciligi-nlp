import styles from "./page.module.css";
import {
  ProfitRateChart,
  TermChart,
  CostChart,
} from "../../components/ComparisonCharts";

export default function ComparePage() {
  return (
    <main className={styles.main}>
      <section className={styles.pageHeader}>
        <div>
          <h1 className={styles.title}>Ürün Karşılaştırma</h1>
          <p className={styles.description}>
            Katılım bankalarının benzer ürünlerini tek ekranda karşılaştırın.
          </p>
        </div>

        <div className={styles.decorativeLines}>
          <span className={styles.lineTurquoise}></span>
          <span className={styles.lineYellow}></span>
        </div>
      </section>

      <section className={styles.filterCard}>
        <div className={styles.filterGroup}>
          <label htmlFor="bank">Banka Seçimi</label>

          <div className={styles.selectWrapper}>
            <span className={styles.selectIcon}>🏛</span>

            <select id="bank" className={styles.select}>
              <option>
                Kuveyt Türk, Albaraka Türk, Türkiye Finans, Vakıf Katılım
              </option>
            </select>
          </div>
        </div>

        <div className={styles.filterGroup}>
          <label htmlFor="product">Ürün Türü</label>

          <div className={styles.selectWrapper}>
            <span className={styles.selectIcon}>🚗</span>

            <select id="product" className={styles.select}>
              <option>Taşıt Finansmanı</option>
            </select>
          </div>
        </div>

        <button className={styles.compareButton}>
          <span className={styles.compareIcon}>⚖</span>
          Karşılaştır
        </button>
      </section>
      <section className={styles.comparisonCard}>
  <h2 className={styles.sectionTitle}>Karşılaştırma Tablosu</h2>

  <div className={styles.tableWrapper}>
    <table className={styles.comparisonTable}>
      <thead>
        <tr>
          <th>Banka</th>
          <th>Kampanya</th>
          <th>Kâr Payı Oranı</th>
          <th>Vade</th>
          <th>Taksit</th>
          <th>Masraf</th>
          <th>Avantaj</th>
        </tr>
      </thead>

      <tbody>
        <tr>
          <td><strong>Kuveyt Türk</strong></td>
          <td>Taşıt Finansmanı Özel Oran Kampanyası</td>
          <td>
            <span className={styles.bestRate}>%2,49</span>
            <span className={`${styles.badge} ${styles.turquoiseBadge}`}>
              En Düşük
            </span>
          </td>
          <td>24 Ay</td>
          <td>24</td>
          <td>0 TL</td>
          <td>
            <span className={`${styles.badge} ${styles.turquoiseBadge}`}>
              Düşük oran
            </span>
          </td>
        </tr>

        <tr>
          <td><strong>Albaraka Türk</strong></td>
          <td>Davet Et Kazan Kampanyası</td>
          <td>%2,69</td>
          <td>36 Ay</td>
          <td>36</td>
          <td>0 TL</td>
          <td>
            <span className={`${styles.badge} ${styles.yellowBadge}`}>
              Masrafsız
            </span>
          </td>
        </tr>

        <tr>
          <td><strong>Türkiye Finans</strong></td>
          <td>Katılma Hesabı Hoş Geldin Kampanyası</td>
          <td>%2,79</td>
          <td>48 Ay</td>
          <td>48</td>
          <td>250 TL</td>
          <td>
            <span className={`${styles.badge} ${styles.turquoiseBadge}`}>
              Uzun vade
            </span>
          </td>
        </tr>

        <tr>
          <td><strong>Vakıf Katılım</strong></td>
          <td>Otomobil Finansmanı Avantajlı Paket</td>
          <td>%2,89</td>
          <td>36 Ay</td>
          <td>36</td>
          <td>250 TL</td>
          <td>
            <span className={`${styles.badge} ${styles.yellowBadge}`}>
              Esnek vade
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</section>
<section className={styles.chartsGrid}>
  <div className={styles.chartCard}>
    <h2 className={styles.sectionTitle}>
      Kâr Payı Oranı Karşılaştırması
    </h2>

    <div className={styles.chartContainer}>
    <ProfitRateChart />
    </div>
  </div>

  <div className={styles.chartCard}>
    <h2 className={styles.sectionTitle}>
      Vade ve Masraf Karşılaştırması
    </h2>

    <div className={styles.dualCharts}>
  <div className={styles.smallChart}>
    <TermChart />
  </div>

  <div className={styles.chartDivider}></div>

  <div className={styles.smallChart}>
    <CostChart />
  </div>
</div>
</div>
</section>
    </main>
  );
}