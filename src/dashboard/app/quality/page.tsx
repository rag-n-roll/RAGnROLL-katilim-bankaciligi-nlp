"use client";

import { useEffect, useState } from "react";
import { getMetricsSummary } from "../../services/api";
import styles from "../live.module.css";

type Metrics = Awaited<ReturnType<typeof getMetricsSummary>>;
const CONTEXT_LABELS: Record<string, string> = {
  UYGULAMA_KANALI: "Kanal",
  KART_ADI: "Kart adı",
  MUSTERI_HITABI: "Müşteri hitabı",
};

export default function QualityPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMetricsSummary().then(setMetrics).catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <div><h1>Veri kalitesi</h1><p>Eksiklik, kanıt kapsamı, doğrulanmış zenginleştirme ve tekrar kümeleri.</p></div>
      </header>
      {error && <p className={styles.error} role="alert">{error}</p>}
      {!metrics && !error && <p className={styles.status}>Kalite metrikleri yükleniyor…</p>}
      {metrics && (
        <>
          <section className={styles.cards}>
            <article className={styles.card}><span className={styles.muted}>Kayıt</span><strong className={styles.metric}>{metrics.data_quality.record_count}</strong></article>
            <article className={styles.card}><span className={styles.muted}>Tekrar kümesi</span><strong className={styles.metric}>{metrics.data_quality.duplicate_cluster_count}</strong></article>
            <article className={styles.card}><span className={styles.muted}>Ham kanıt kapsamı</span><strong className={styles.metric}>%{(metrics.data_quality.evidence_coverage * 100).toFixed(1).replace(".", ",")}</strong></article>
            <article className={styles.card}><span className={styles.muted}>Zenginleştirilmiş kapsam</span><strong className={styles.metric}>%{(metrics.data_quality.enriched_evidence_coverage * 100).toFixed(1).replace(".", ",")}</strong></article>
          </section>
          <section className={styles.grid}>
            <article className={styles.card}>
              <h2>Alan durumları</h2>
              <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Durum</th><th>Alan sayısı</th></tr></thead><tbody>{Object.entries(metrics.data_quality.field_statuses).map(([status, count]) => <tr key={status}><td><span className={styles.badge}>{status}</span></td><td>{count}</td></tr>)}</tbody></table></div>
            </article>
            <article className={styles.card}>
              <h2>Çalışma zamanı metrikleri</h2>
              <p className={styles.muted}>Doğrulanmış kazanım: {metrics.data_quality.verified_enrichment_fields} alan · Kurtarılan çıkarım hatası: {metrics.data_quality.recovered_extraction_failures}</p>
              <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Olay</th><th>Adet</th><th>Hata</th><th>p95</th></tr></thead><tbody>{Object.entries(metrics.observability.events).map(([event, item]) => <tr key={event}><td>{event}</td><td>{item.count}</td><td>%{Math.round(item.error_rate * 100)}</td><td>{item.p95_latency_ms ?? "—"} ms</td></tr>)}</tbody></table></div>
            </article>
            <article className={`${styles.card} ${styles.contextQualityCard}`}>
              <h2>Doğrulanmış bağlam varlıkları</h2>
              <p className={styles.muted}>Geçerlilik tarihi bulunmayan {metrics.data_quality.temporal_observation_count} kayıtta çekim tarihi, yalnız kaynakta görülme kanıtı olarak saklanır.</p>
              <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Varlık</th><th>Adet</th></tr></thead><tbody>{Object.entries(metrics.data_quality.grounded_entity_counts).map(([label, count]) => <tr key={label}><td><span className={styles.badge}>{CONTEXT_LABELS[label] ?? label}</span></td><td>{count}</td></tr>)}</tbody></table></div>
            </article>
          </section>
        </>
      )}
    </main>
  );
}
