"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getDashboardSnapshot } from "../services/api";
import styles from "./live.module.css";

type Snapshot = Awaited<ReturnType<typeof getDashboardSnapshot>>;

export default function HomePage() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getDashboardSnapshot()
      .then(setSnapshot)
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <div>
          <h1>Katılım bankacılığı bilgi platformu</h1>
          <p>
            Güncel kampanyaları yapılandırılmış alanlar ve kaynak kanıtlarıyla
            inceleyin.
          </p>
        </div>
        <Link className={styles.button} href="/chatbot">
          Kanıta dayalı asistana sor
        </Link>
      </header>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {!snapshot && !error && (
        <p className={styles.status}>Canlı veriler yükleniyor…</p>
      )}
      {snapshot && (
        <>
          <section className={styles.cards} aria-label="Özet metrikler">
            <article className={styles.card}>
              <span className={styles.muted}>Banka</span>
              <strong className={styles.metric}>{snapshot.summary.bank_count}</strong>
            </article>
            <article className={styles.card}>
              <span className={styles.muted}>Kampanya</span>
              <strong className={styles.metric}>
                {snapshot.summary.campaign_count}
              </strong>
            </article>
            <article className={styles.card}>
              <span className={styles.muted}>Toplam kayıt</span>
              <strong className={styles.metric}>
                {snapshot.summary.record_count}
              </strong>
            </article>
            <article className={styles.card}>
              <span className={styles.muted}>Ortalama kâr payı</span>
              <strong className={styles.metric}>
                {snapshot.summary.average_profit_share_rate === null
                  ? "Belirtilmemiş"
                  : `%${(
                      snapshot.summary.average_profit_share_rate * 100
                    ).toFixed(2)}`}
              </strong>
            </article>
          </section>
          <section className={styles.grid}>
            <article className={styles.card}>
              <h2>Bankalara göre kampanya dağılımı</h2>
              {snapshot.distributions.banks.map((bank) => (
                <div className={styles.barRow} key={bank.slug}>
                  <span>{bank.name}</span>
                  <div className={styles.bar}>
                    <span
                      style={{
                        width: `${Math.max(bank.campaign_share * 100, 2)}%`,
                      }}
                    />
                  </div>
                  <strong>{bank.campaign_count}</strong>
                </div>
              ))}
            </article>
            <article className={styles.card}>
              <h2>Son güncellenen kampanyalar</h2>
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr><th>Banka</th><th>Kampanya</th><th>Tür</th></tr>
                  </thead>
                  <tbody>
                    {snapshot.recent_campaigns.map((item) => (
                      <tr key={item.id}>
                        <td>{item.bank_name}</td>
                        <td>{item.title}</td>
                        <td>{item.product_type ?? "Belirtilmemiş"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </section>
        </>
      )}
    </main>
  );
}
