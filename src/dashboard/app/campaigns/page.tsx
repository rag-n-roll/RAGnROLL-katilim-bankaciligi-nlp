import styles from "./page.module.css";

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

const tableRows = [
  {
    bank: "Kuveyt Türk",
    initials: "KT",
    campaign: "Taşıt Finansmanı Özel Oran Kampanyası",
    type: "Finansman",
    rate: "%2,49",
    term: "24 Ay",
    cost: "0 TL",
    validity: "20 Mayıs 2024 – 30 Haziran 2024",
    best: true,
  },
  {
    bank: "Albaraka Türk",
    initials: "AT",
    campaign: "Davet Et Kazan Kampanyası",
    type: "Kart",
    rate: "%2,69",
    term: "36 Ay",
    cost: "0 TL",
    validity: "19 Mayıs 2024 – 30 Haziran 2024",
  },
  {
    bank: "Türkiye Finans",
    initials: "TF",
    campaign: "Katılma Hesabı Hoş Geldin Kampanyası",
    type: "Yatırım",
    rate: "%2,79",
    term: "48 Ay",
    cost: "250 TL",
    validity: "18 Mayıs 2024 – 30 Haziran 2024",
  },
  {
    bank: "Vakıf Katılım",
    initials: "VK",
    campaign: "Otomobil Finansmanı Avantajlı Paket",
    type: "Finansman",
    rate: "%2,89",
    term: "36 Ay",
    cost: "250 TL",
    validity: "17 Mayıs 2024 – 30 Haziran 2024",
  },
  {
    bank: "Ziraat Katılım",
    initials: "ZK",
    campaign: "Esnek Hesap Açılış Kampanyası",
    type: "Yatırım",
    rate: "%2,59",
    term: "24 Ay",
    cost: "0 TL",
    validity: "16 Mayıs 2024 – 30 Haziran 2024",
  },
];

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

      <section className={styles.campaignWorkspace}>
        {/* SOL KART */}
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Banka Bazlı Tüm Kampanyalar</h2>

            <span className={styles.campaignCount}>25 kampanya</span>
          </div>

          <div className={styles.campaignList}>
            {campaigns.map((campaign) => (
              <div
                key={campaign.bank}
                className={`${styles.campaignRow} ${
                  campaign.selected ? styles.selectedCampaign : ""
                }`}
              >
                <div className={styles.bankIcon}>{campaign.initials}</div>

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

          <button className={styles.viewAllButton}>
            Tümünü Görüntüle <span>›</span>
          </button>
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
      </section>

      {/* ALT TABLO */}
      <section className={styles.tableCard}>
        <h2>Yapılandırılmış Veri Tablosu</h2>

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
              {tableRows.map((row) => (
                <tr key={row.bank}>
                  <td>
                    <div className={styles.tableBank}>
                      <span className={styles.smallBankIcon}>
                        {row.initials}
                      </span>

                      <strong>{row.bank}</strong>
                    </div>
                  </td>

                  <td className={styles.campaignCell}>{row.campaign}</td>

                  <td>
                    <span
                      className={`${styles.typeBadge} ${getTypeClass(row.type)}`}
                    >
                      {row.type}
                    </span>
                  </td>

                  <td>
                    <strong>{row.rate}</strong>

                    {row.best && (
                      <span className={styles.bestBadge}>En Düşük</span>
                    )}
                  </td>

                  <td>{row.term}</td>
                  <td>{row.cost}</td>
                  <td>{row.validity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}