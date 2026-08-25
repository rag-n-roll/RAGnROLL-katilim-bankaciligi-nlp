"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import BankLogo from "../components/BankLogo";
import { getDashboardSnapshot } from "../services/api";
import styles from "./live.module.css";

type Snapshot = Awaited<ReturnType<typeof getDashboardSnapshot>>;

function formatUpdatedAt(value: string | null) {
  if (!value) return "Güncelleme zamanı belirtilmemiş";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export default function HomePage() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getDashboardSnapshot()
      .then(setSnapshot)
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <main className={`${styles.main} ${styles.homePage}`}>
      <section className={styles.hero} aria-labelledby="home-title">
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>Kanıta dayalı finansal keşif</span>
          <h1 id="home-title">
            Katılım bankacılığındaki seçenekleri tek pusulada görün.
          </h1>
          <p>
            Canlı kampanya verisini, açıklanabilir karşılaştırmayı ve kaynaklara
            bağlı asistan yanıtlarını aynı çalışma alanında inceleyin.
          </p>
          <div className={styles.heroActions}>
            <Link className={styles.button} href="/campaigns">
              Kampanyaları incele <span aria-hidden="true">→</span>
            </Link>
            <Link className={styles.secondaryButton} href="/chatbot">
              <span aria-hidden="true">✦</span> Kanıta dayalı asistana sor
            </Link>
          </div>
        </div>
        <div className={styles.heroVisual} aria-hidden="true">
          <div className={styles.heroCompass}>
            <span className={styles.compassNorth}>N</span>
            <span className={styles.compassNeedle} />
            <strong>Pusula</strong>
            <small>veri · kanıt · karar</small>
          </div>
          <span className={styles.orbitLabelOne}>Canlı veri</span>
          <span className={styles.orbitLabelTwo}>Kaynak kanıtı</span>
          <span className={styles.orbitLabelThree}>Açıklanabilir sonuç</span>
        </div>
      </section>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {!snapshot && !error && (
        <p className={styles.status} role="status">Canlı veriler yükleniyor…</p>
      )}
      {snapshot && (
        <>
          <div className={styles.sectionHeading}>
            <div>
              <span className={styles.eyebrow}>Canlı görünüm</span>
              <h2>Platform özeti</h2>
            </div>
            <span className={styles.updatedAt}>
              Son güncelleme: {formatUpdatedAt(snapshot.summary.last_updated_at)}
            </span>
          </div>
          <section className={styles.cards} aria-label="Özet metrikler">
            <article className={`${styles.card} ${styles.metricCard}`}>
              <span className={styles.metricLabel}>Banka</span>
              <strong className={styles.metric}>{snapshot.summary.bank_count}</strong>
            </article>
            <article className={`${styles.card} ${styles.metricCard}`}>
              <span className={styles.metricLabel}>Kampanya</span>
              <strong className={styles.metric}>
                {snapshot.summary.campaign_count}
              </strong>
            </article>
            <article className={`${styles.card} ${styles.metricCard}`}>
              <span className={styles.metricLabel}>Toplam kayıt</span>
              <strong className={styles.metric}>
                {snapshot.summary.record_count}
              </strong>
            </article>
            <article className={`${styles.card} ${styles.metricCard}`}>
              <span className={styles.metricLabel}>Ortalama kâr payı</span>
              <strong className={styles.metric}>
                {snapshot.summary.average_profit_share_rate === null
                  ? "Belirtilmemiş"
                  : `%${(
                      snapshot.summary.average_profit_share_rate * 100
                    ).toFixed(2)}`}
              </strong>
            </article>
          </section>
          <section className={styles.grid} aria-label="Canlı kampanya görünümü">
            <article className={styles.card}>
              <div className={styles.cardHeading}>
                <div>
                  <span className={styles.eyebrow}>Dağılım</span>
                  <h2>Bankalara göre kampanyalar</h2>
                </div>
              </div>
              <div className={styles.distributionList} role="list">
                {snapshot.distributions.banks.map((bank) => {
                  const share = Math.min(100, Math.max(bank.campaign_share * 100, 0));
                  return (
                    <div className={styles.barRow} key={bank.slug} role="listitem">
                      <span className={styles.bankIdentity}>
                        <BankLogo bank={bank.name} decorative size={34} />
                        <span>{bank.name}</span>
                      </span>
                      <span
                        aria-label={`${bank.name}: ${bank.campaign_count} kampanya, yüzde ${share.toFixed(1)}`}
                        className={styles.bar}
                        role="img"
                      >
                        <span style={{ width: `${share}%` }} />
                      </span>
                      <strong>{bank.campaign_count}</strong>
                    </div>
                  );
                })}
                {snapshot.distributions.banks.length === 0 && (
                  <p className={styles.muted}>Banka dağılımı henüz oluşmadı.</p>
                )}
              </div>
            </article>
            <article className={styles.card}>
              <div className={styles.cardHeading}>
                <div>
                  <span className={styles.eyebrow}>Yeni hareketler</span>
                  <h2>Son güncellenen kampanyalar</h2>
                </div>
              </div>
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <caption className={styles.visuallyHidden}>
                    Son güncellenen kampanyalar
                  </caption>
                  <thead>
                    <tr><th>Banka</th><th>Kampanya</th><th>Tür</th></tr>
                  </thead>
                  <tbody>
                    {snapshot.recent_campaigns.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <span className={styles.bankIdentity}>
                            <BankLogo bank={item.bank_name} decorative size={30} />
                            <span>{item.bank_name}</span>
                          </span>
                        </td>
                        <td>{item.title}</td>
                        <td>{item.product_type ?? "Belirtilmemiş"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {snapshot.recent_campaigns.length === 0 && (
                <p className={styles.muted}>Henüz güncel kampanya bulunmuyor.</p>
              )}
            </article>
          </section>
        </>
      )}
    </main>
  );
}
