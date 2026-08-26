"use client";

import { useEffect, useMemo, useState } from "react";
import styles from "./page.module.css";
import {
  CostChart,
  ProfitRateChart,
  TermChart,
  type ComparisonChartItem,
} from "../../components/ComparisonCharts";
import BankLogo from "../../components/BankLogo";
import {
  getFinancingCampaigns,
  getFinancingQuotes,
  type FinancingCampaign,
  type FinancingQuote,
  type FinancingQuoteResponse,
  type FinancingType,
} from "../../services/api";

const BANKS = [
  { slug: "kuveyt-turk", name: "Kuveyt Türk" },
  { slug: "albaraka-turk", name: "Albaraka Türk" },
  { slug: "turkiye-finans", name: "Türkiye Finans" },
  { slug: "vakif-katilim", name: "Vakıf Katılım" },
  { slug: "ziraat-katilim", name: "Ziraat Katılım" },
  { slug: "emlak-katilim", name: "Emlak Katılım" },
  { slug: "hayat-finans", name: "Hayat Finans" },
  { slug: "tom-katilim", name: "TOM Katılım" },
  { slug: "dunya-katilim", name: "Dünya Katılım" },
  { slug: "adil-katilim", name: "Adil Katılım" },
] as const;

const FINANCING_TYPES: Array<{ value: FinancingType; label: string }> = [
  { value: "vehicle", label: "Taşıt finansmanı" },
  { value: "housing", label: "Konut finansmanı" },
  { value: "consumer", label: "İhtiyaç finansmanı" },
  { value: "commercial", label: "Ticari finansman" },
];

const money = new Intl.NumberFormat("tr-TR", {
  style: "currency",
  currency: "TRY",
  maximumFractionDigits: 2,
});

const number = new Intl.NumberFormat("tr-TR", {
  maximumFractionDigits: 2,
});

function shortBankName(value: string) {
  return value
    .replace(" KATILIM BANKASI A.Ş.", "")
    .replace(" BANKASI A.Ş.", "")
    .replace(" KATILIM BANKASI A.Ş", "")
    .trim();
}

function quoteStatus(quote: FinancingQuote) {
  if (
    quote.status === "available" &&
    quote.calculation_origin !== "last_verified_official_rate"
  ) {
    return "Doğrulanmış teklif";
  }
  if (quote.calculation_origin === "last_verified_official_rate") {
    return "Son doğrulanmış oran";
  }
  return "Karşılaştırılabilir teklif yok";
}

export default function ComparePage() {
  const [selectedBanks, setSelectedBanks] = useState<string[]>(
    BANKS.map((bank) => bank.slug)
  );
  const [financingType, setFinancingType] =
    useState<FinancingType>("vehicle");
  const [campaigns, setCampaigns] = useState<FinancingCampaign[]>([]);
  const [campaignKey, setCampaignKey] = useState("");
  const [campaignsLoading, setCampaignsLoading] = useState(true);
  const [campaignError, setCampaignError] = useState("");
  const [financingAmount, setFinancingAmount] = useState(150_000);
  const [termMonths, setTermMonths] = useState(24);
  const [feePriority, setFeePriority] = useState(true);
  const [result, setResult] = useState<FinancingQuoteResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getFinancingCampaigns()
      .then((response) => {
        if (!active) return;
        setCampaigns(response.campaigns);
        setCampaignError("");
      })
      .catch(() => {
        if (active) {
          setCampaignError(
            "Kampanya kataloğu alınamadı; finansman türüyle karşılaştırabilirsiniz."
          );
        }
      })
      .finally(() => {
        if (active) setCampaignsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const matchingCampaigns = useMemo(
    () =>
      campaigns.filter(
        (campaign) => campaign.financing_type === financingType
      ),
    [campaigns, financingType]
  );

  const toggleBank = (slug: string) => {
    setSelectedBanks((current) =>
      current.includes(slug)
        ? current.filter((item) => item !== slug)
        : [...current, slug]
    );
    setResult(null);
  };

  const handleCompare = async () => {
    if (
      !Number.isFinite(financingAmount) ||
      financingAmount <= 0 ||
      !Number.isInteger(termMonths) ||
      termMonths < 1 ||
      termMonths > 240
    ) {
      setError("Geçerli bir finansman tutarı ve 1–240 ay arası vade girin.");
      setResult(null);
      return;
    }
    if (selectedBanks.length === 0) {
      setError("Karşılaştırmak için en az bir banka seçin.");
      setResult(null);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const response = await getFinancingQuotes({
        financing_type: campaignKey ? undefined : financingType,
        campaign_key: campaignKey || undefined,
        amount: financingAmount,
        term_months: termMonths,
        fee_priority: feePriority,
      });
      setResult(response);
      requestAnimationFrame(() => {
        document
          .getElementById("comparison-results")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } catch (caught) {
      setResult(null);
      setError(
        caught instanceof Error
          ? caught.message
          : "Doğrulanmış teklifler şu anda alınamadı."
      );
    } finally {
      setLoading(false);
    }
  };

  const displayedQuotes = useMemo(
    () =>
      (result?.quotes ?? []).filter((quote) =>
        selectedBanks.includes(quote.bank_slug)
      ),
    [result, selectedBanks]
  );

  const availableQuotes = displayedQuotes.filter(
    (quote) =>
      quote.status === "available" &&
      quote.calculation_origin !== "last_verified_official_rate" &&
      typeof quote.monthly_installment === "number" &&
      typeof quote.total_repayment === "number"
  );

  const rateChartItems: ComparisonChartItem[] = availableQuotes
    .filter((quote) => typeof quote.monthly_profit_rate === "number")
    .map((quote) => ({
      bank: shortBankName(quote.bank_name),
      rate: quote.monthly_profit_rate,
    }));

  const termChartItems: ComparisonChartItem[] = availableQuotes.map(
    (quote) => ({
      bank: shortBankName(quote.bank_name),
      term: termMonths,
    })
  );

  const costChartItems: ComparisonChartItem[] = availableQuotes
    .filter((quote) => typeof quote.fees_total === "number")
    .map((quote) => ({
      bank: shortBankName(quote.bank_name),
      cost: quote.fees_total,
    }));

  const leadingSlug = availableQuotes[0]?.bank_slug;

  return (
    <main className={styles.main}>
      <section className={styles.pageHeader}>
        <div>
          <h1 className={styles.title}>Finansman Karşılaştırma</h1>
          <p className={styles.description}>
            Katılım bankalarının kaynaklı tekliflerini aynı tutar ve vadede inceleyin.
          </p>
        </div>
        <div className={styles.decorativeLines} aria-hidden="true">
          <span />
          <span />
        </div>
      </section>

      <section
        className={styles.selectionSection}
        aria-label="Finansman karşılaştırma seçenekleri"
      >
        <div className={styles.selectionIntro}>
          <h2>Tutarı, vadeyi ve önceliğinizi belirleyin.</h2>
          <p>Sonuçlar yalnız resmî banka kaynaklarıyla doğrulanabilen verilerden oluşur.</p>
        </div>

        <div className={styles.field}>
          <span>
            Bankalar <small>{selectedBanks.length}/10</small>
          </span>
          <details className={styles.bankPicker}>
            <summary>
              <span className={styles.selectedLogos}>
                {BANKS.filter((bank) => selectedBanks.includes(bank.slug))
                  .slice(0, 4)
                  .map((bank) => (
                    <BankLogo bank={bank.name} size={24} key={bank.slug} />
                  ))}
                <b>
                  {selectedBanks.length
                    ? selectedBanks.length + " banka seçildi"
                    : "Banka seçiniz"}
                </b>
              </span>
              <i>⌄</i>
            </summary>
            <div className={styles.bankOptions}>
              {BANKS.map((bank) => (
                <label key={bank.slug}>
                  <input
                    type="checkbox"
                    checked={selectedBanks.includes(bank.slug)}
                    onChange={() => toggleBank(bank.slug)}
                  />
                  <BankLogo bank={bank.name} size={28} />
                  <span>{bank.name}</span>
                </label>
              ))}
            </div>
          </details>
        </div>

        <label className={styles.field}>
          <span>Finansman türü</span>
          <select
            value={financingType}
            onChange={(event) => {
              setFinancingType(event.target.value as FinancingType);
              setCampaignKey("");
              setResult(null);
            }}
          >
            {FINANCING_TYPES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.field}>
          <span>
            Kampanya <small>isteğe bağlı</small>
          </span>
          <select
            value={campaignKey}
            disabled={campaignsLoading}
            onChange={(event) => {
              setCampaignKey(event.target.value);
              setResult(null);
            }}
          >
            <option value="">
              {campaignsLoading
                ? "Kampanyalar yükleniyor…"
                : "Tüm uygun banka ürünleri"}
            </option>
            {matchingCampaigns.map((campaign) => (
              <option key={campaign.campaign_key} value={campaign.campaign_key}>
                {campaign.display_name} · {campaign.bank_products.length} banka
              </option>
            ))}
          </select>
        </label>

        <label className={styles.field}>
          <span>Finansman tutarı</span>
          <div className={styles.numberField}>
            <input
              aria-label="Finansman tutarı"
              inputMode="numeric"
              min={1_000}
              max={100_000_000}
              step={1_000}
              type="number"
              value={financingAmount}
              onChange={(event) => {
                setFinancingAmount(Number(event.target.value));
                setResult(null);
              }}
            />
            <b>TL</b>
          </div>
        </label>

        <label className={styles.field}>
          <span>Vade</span>
          <div className={styles.numberField}>
            <input
              aria-label="Vade"
              inputMode="numeric"
              min={1}
              max={240}
              type="number"
              value={termMonths}
              onChange={(event) => {
                setTermMonths(Number(event.target.value));
                setResult(null);
              }}
            />
            <b>Ay</b>
          </div>
        </label>

        <label className={styles.priorityToggle}>
          <input
            type="checkbox"
            checked={feePriority}
            onChange={(event) => {
              setFeePriority(event.target.checked);
              setResult(null);
            }}
          />
          <span>
            <b>Masraf önceliğim var</b>
            <small>Bilinen düşük masraflı teklifler önce gösterilir.</small>
          </span>
        </label>

        <button
          type="button"
          className={styles.compareButton}
          onClick={handleCompare}
          disabled={loading}
        >
          {loading ? "Kaynaklar kontrol ediliyor…" : "Teklifleri karşılaştır"}
          <span>→</span>
        </button>

        {(error || campaignError) && (
          <div className={styles.formNotice} role={error ? "alert" : "status"}>
            <strong>{error ? "Doğrulanmış teklifler alınamadı" : "Katalog bilgisi"}</strong>
            <span>{error || campaignError}</span>
            {error && (
              <button type="button" onClick={handleCompare}>
                Yeniden dene →
              </button>
            )}
          </div>
        )}
      </section>

      <section
        className={styles.resultsState}
        id="comparison-results"
        aria-live="polite"
      >
        {!result ? (
          <div className={styles.emptyState}>
            <span aria-hidden="true">↗</span>
            <div>
              <h2>Karşılaştırmaya hazır</h2>
              <p>Bilgileri girip teklifleri karşılaştırın; çevrimdışı finansal satır üretilmez.</p>
            </div>
          </div>
        ) : availableQuotes.length === 0 ? (
          <div className={styles.emptyState}>
            <span aria-hidden="true">i</span>
            <div>
              <h2>Doğrulanmış teklif bulunamadı</h2>
              <p>Seçilen tutar, vade ve bankalar için resmî kaynağı olan karşılaştırılabilir sonuç yok.</p>
            </div>
          </div>
        ) : (
          <div className={styles.coverageStrip}>
            <strong>{availableQuotes.length} doğrulanmış teklif</strong>
            <span>
              {displayedQuotes.length} banka sonucu · öncelik: {feePriority ? "masraf" : "aylık taksit"}
            </span>
            <time dateTime={result.generated_at}>
              {new Date(result.generated_at).toLocaleString("tr-TR")}
            </time>
          </div>
        )}
      </section>

      {result && availableQuotes.length > 0 && (
        <section className={styles.visualSection}>
          <div className={styles.visualInner}>
            <div className={styles.profitArea}>
              <div className={styles.graphTitle}>
                <h3>Kâr payı oranı</h3>
                <p>Yalnız sayısal oranı doğrulanan canlı teklifler</p>
              </div>
              {rateChartItems.length ? (
                <div className={styles.profitChart}>
                  <ProfitRateChart items={rateChartItems} />
                </div>
              ) : (
                <p className={styles.chartEmpty}>Doğrulanmış oran verisi yok.</p>
              )}
            </div>

            <div className={styles.termCostArea}>
              <div className={styles.graphTitle}>
                <h3>Vade ve masraf</h3>
                <p>Seçilen ortak vade ve yalnız yayımlanmış masraf bilgileri</p>
              </div>
              <div className={styles.dualCharts}>
                <div>
                  <TermChart items={termChartItems} />
                </div>
                <span />
                <div>
                  {costChartItems.length ? (
                    <CostChart items={costChartItems} />
                  ) : (
                    <p className={styles.chartEmpty}>Doğrulanmış masraf verisi yok.</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {result && (
        <section className={styles.tableSection}>
          <div className={styles.tableHeading}>
            <div>
              <h2>Kaynaklı teklif tablosu</h2>
            </div>
            <p>Eksik bankalar gizlenmez; neden karşılaştırılamadıkları gösterilir.</p>
          </div>
          <div className={styles.tableWrapper}>
            <table className={styles.comparisonTable}>
              <thead>
                <tr>
                  <th>Banka / ürün</th>
                  <th>Kâr payı</th>
                  <th>Aylık taksit</th>
                  <th>Toplam ödeme</th>
                  <th>Masraf</th>
                  <th>Durum / kaynak</th>
                </tr>
              </thead>
              <tbody>
                {displayedQuotes.map((quote) => (
                  <tr
                    key={quote.bank_slug}
                    className={
                      quote.status === "available"
                        ? undefined
                        : styles.unavailableRow
                    }
                  >
                    <td>
                      <span className={styles.bankCell}>
                        <BankLogo bank={quote.bank_name} size={34} />
                        <span>
                          <strong>{shortBankName(quote.bank_name)}</strong>
                          <small>{quote.product_name || "Finansman verisi"}</small>
                        </span>
                      </span>
                    </td>
                    <td>
                      <strong
                        className={
                          quote.bank_slug === leadingSlug
                            ? styles.bestRate
                            : undefined
                        }
                      >
                        {typeof quote.monthly_profit_rate === "number"
                          ? "%" + number.format(quote.monthly_profit_rate)
                          : "—"}
                      </strong>
                    </td>
                    <td>
                      {typeof quote.monthly_installment === "number"
                        ? money.format(quote.monthly_installment)
                        : "—"}
                    </td>
                    <td>
                      {typeof quote.total_repayment === "number"
                        ? money.format(quote.total_repayment)
                        : "—"}
                    </td>
                    <td>
                      {typeof quote.fees_total === "number"
                        ? money.format(quote.fees_total)
                        : "Belirtilmemiş"}
                    </td>
                    <td>
                      <span
                        className={
                          quote.status === "available"
                            ? styles.goldBadge
                            : styles.softBadge
                        }
                      >
                        {quoteStatus(quote)}
                      </span>
                      <small className={styles.statusMessage}>{quote.message}</small>
                      {quote.source_url && (
                        <a
                          className={styles.sourceLink}
                          href={quote.source_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Resmî kaynak →
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={styles.disclaimer}>
            <span aria-hidden="true">i</span>
            {result.disclaimer}
          </p>
        </section>
      )}
    </main>
  );
}
