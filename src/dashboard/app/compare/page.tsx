"use client";

import { FormEvent, useEffect, useState } from "react";
import { compareCampaigns, getFilters } from "../../services/api";
import styles from "../live.module.css";

type Comparison = Awaited<ReturnType<typeof compareCampaigns>>;
type Filters = Awaited<ReturnType<typeof getFilters>>;

export default function ComparePage() {
  const [filters, setFilters] = useState<Filters | null>(null);
  const [product, setProduct] = useState("financing");
  const [currency, setCurrency] = useState("TRY");
  const [result, setResult] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getFilters()
      .then((value) => {
        setFilters(value);
        if (value.product_types[0]) setProduct(value.product_types[0].value);
        if (value.currencies[0]) setCurrency(value.currencies[0].value);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      setResult(await compareCampaigns({ product_type: product, currency, limit: 200 }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Karşılaştırma yapılamadı.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <div>
          <h1>Açıklanabilir karşılaştırma</h1>
          <p>Eksik değerler sıfır sayılmaz; sıralama gerekçesi ve eksik ölçütler açıkça gösterilir.</p>
        </div>
      </header>
      <form className={styles.controls} onSubmit={submit}>
        <select aria-label="Ürün türü" value={product} onChange={(event) => setProduct(event.target.value)} required>
          {filters?.product_types.map((item) => <option key={item.value} value={item.value}>{item.label} ({item.count})</option>)}
        </select>
        <select aria-label="Para birimi" value={currency} onChange={(event) => setCurrency(event.target.value)} required>
          {(filters?.currencies.length ? filters.currencies : [{ value: "TRY", label: "TRY", count: 0 }]).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
        <button className={styles.button} disabled={loading || !product} type="submit">{loading ? "Karşılaştırılıyor…" : "Karşılaştır"}</button>
      </form>
      {error && <p className={styles.error} role="alert">{error}</p>}
      {!result && !error && <p className={styles.status}>Filtreleri seçip karşılaştırmayı başlatın.</p>}
      {result && (
        <section className={styles.card}>
          <h2>Karşılaştırma sonucu</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr><th>Sıra</th><th>Kampanya</th><th>Avantaj skoru</th><th>Veri kapsamı</th><th>Gerekçe</th><th>Eksik ölçütler</th></tr></thead>
              <tbody>
                {result.included.map((item, index) => (
                  <tr key={item.id}>
                    <td>{index + 1}</td>
                    <td><strong>{item.title}</strong><br /><span className={styles.muted}>{item.id}</span></td>
                    <td>{item.advantage_score === null ? "Hesaplanamadı" : `${Math.round(item.advantage_score * 100)} / 100`}</td>
                    <td>%{Math.round(item.comparison_confidence * 100)}</td>
                    <td>{item.ranking_reason}</td>
                    <td>{item.missing_fields.length ? item.missing_fields.join(", ") : "Yok"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.included.length === 0 && <p className={styles.muted}>Karşılaştırılabilir kayıt bulunamadı.</p>}
          <p className={styles.muted}>{result.excluded.length} kayıt ölçüt uyuşmazlığı nedeniyle dışarıda bırakıldı.</p>
        </section>
      )}
    </main>
  );
}
