"use client";

import { FormEvent, useEffect, useState } from "react";
import BankLogo from "../../components/BankLogo";
import {
  Campaign,
  getCampaignDetail,
  getCampaigns,
  getFilters,
} from "../../services/api";
import styles from "../live.module.css";

type Filters = Awaited<ReturnType<typeof getFilters>>;

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

export default function CampaignsPage() {
  const [filters, setFilters] = useState<Filters | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selected, setSelected] = useState<Campaign | null>(null);
  const [bank, setBank] = useState("");
  const [product, setProduct] = useState("");
  const [search, setSearch] = useState("");
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadCampaigns() {
    setLoading(true);
    setError("");
    try {
      const result = await getCampaigns({
        bank_slug: bank,
        product_type: product,
        search: search.trim() || undefined,
        limit: 50,
      });
      setCampaigns(result.items);
      setTotal(result.total);
      if (result.items[0]) {
        setSelected(await getCampaignDetail(result.items[0].id));
      } else {
        setSelected(null);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Kampanyalar yüklenemedi.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    Promise.all([getFilters(), getCampaigns({ limit: 50 })])
      .then(async ([filterResult, campaignResult]) => {
        setFilters(filterResult);
        setCampaigns(campaignResult.items);
        setTotal(campaignResult.total);
        if (campaignResult.items[0]) {
          setSelected(await getCampaignDetail(campaignResult.items[0].id));
        }
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    void loadCampaigns();
  }

  async function selectCampaign(campaign: Campaign) {
    setError("");
    try {
      setSelected(await getCampaignDetail(campaign.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Kampanya detayı yüklenemedi.");
    }
  }

  const fields = Object.entries(selected?.structured?.fields ?? {});

  return (
    <main className={styles.main} aria-busy={loading}>
      <header className={styles.header}>
        <div>
          <span className={styles.eyebrow}>Canlı kampanya kataloğu</span>
          <h1>Kampanya merkezi</h1>
          <p>Ham metni, yapılandırılmış alanı ve alanın kaynak kanıtını birlikte inceleyin.</p>
        </div>
        <span className={styles.headerBadge}>{total} kayıt</span>
      </header>

      <form className={styles.controls} onSubmit={submit} aria-label="Kampanya filtreleri">
        <label className={styles.filterField}>
          <span>Banka</span>
          <select value={bank} onChange={(event) => setBank(event.target.value)}>
            <option value="">Tüm bankalar</option>
            {filters?.banks.map((item) => <option key={item.value} value={item.value}>{item.label} ({item.count})</option>)}
          </select>
        </label>
        <label className={styles.filterField}>
          <span>Ürün türü</span>
          <select value={product} onChange={(event) => setProduct(event.target.value)}>
            <option value="">Tüm ürün türleri</option>
            {filters?.product_types.map((item) => <option key={item.value} value={item.value}>{item.label} ({item.count})</option>)}
          </select>
        </label>
        <label className={styles.filterField}>
          <span>Kampanya ara</span>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Başlıkta ara" minLength={2} />
        </label>
        <button className={styles.button} disabled={loading} type="submit">Filtrele</button>
      </form>

      {error && <p className={styles.error} role="alert">{error}</p>}
      {loading && <p className={styles.status} role="status">Kampanyalar yükleniyor…</p>}
      {!loading && !error && campaigns.length === 0 && <p className={styles.status}>Filtreyle eşleşen kampanya bulunamadı.</p>}

      <section className={styles.campaignGrid} aria-label="Kampanya sonuçları">
        <article className={`${styles.card} ${styles.campaignListCard}`}>
          <div className={styles.cardHeading}>
            <div>
              <span className={styles.eyebrow}>Sonuçlar</span>
              <h2>Kampanyalar</h2>
            </div>
          </div>
          <div className={styles.list}>
            {campaigns.map((campaign) => (
              <button
                className={`${styles.listButton} ${selected?.id === campaign.id ? styles.selected : ""}`}
                aria-pressed={selected?.id === campaign.id}
                key={campaign.id}
                onClick={() => void selectCampaign(campaign)}
                type="button"
              >
                <span className={styles.campaignBank}>
                  <BankLogo bank={campaign.bank_name} decorative size={34} />
                  <strong>{campaign.bank_name}</strong>
                </span>
                <span className={styles.campaignTitle}>{campaign.title}</span>
              </button>
            ))}
          </div>
        </article>
        <article className={`${styles.card} ${styles.campaignDetail}`} aria-live="polite">
          {selected && (
            <div className={styles.detailBank}>
              <BankLogo bank={selected.bank_name} decorative size={42} />
              <span>{selected.bank_name}</span>
            </div>
          )}
          <h2>{selected?.title ?? "Kampanya detayı"}</h2>
          {selected ? (
            <>
              <p className={styles.code}>{selected.content || "Kaynak metin bulunmuyor."}</p>
              <a className={styles.source} href={selected.source_url} rel="noreferrer" target="_blank">
                Resmî kaynağı yeni sekmede aç <span aria-hidden="true">↗</span>
              </a>
            </>
          ) : <p className={styles.muted}>İncelemek için bir kampanya seçin.</p>}
        </article>
      </section>

      {selected && (
        <section className={`${styles.card} ${styles.contractCard}`}>
          <div className={styles.cardHeading}>
            <div>
              <span className={styles.eyebrow}>İzlenebilir veri</span>
              <h2>Alan sözleşmeleri</h2>
            </div>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption className={styles.visuallyHidden}>{selected.title} için yapılandırılmış alanlar</caption>
              <thead><tr><th>Alan</th><th>Değer</th><th>Durum</th><th>Güven</th><th>Kanıt</th></tr></thead>
              <tbody>
                {fields.map(([name, field]) => (
                  <tr key={name}>
                    <td><strong>{name}</strong></td>
                    <td><pre>{displayValue(field.value)}</pre></td>
                    <td><span className={`${styles.badge} ${field.status === "EXPLICIT" ? "" : styles.warningBadge}`}>{field.status}</span></td>
                    <td>{Math.round(field.confidence * 100)}%</td>
                    <td>{field.evidence?.text ?? "Kaynakta belirtilmemiş"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
