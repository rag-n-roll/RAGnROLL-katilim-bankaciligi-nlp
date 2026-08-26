"use client";

import { useMemo, useState } from "react";
import styles from "./page.module.css";
import {
  ProfitRateChart,
  TermChart,
  CostChart,
  type ComparisonChartItem,
} from "../../components/ComparisonCharts";
import BankLogo from "../../components/BankLogo";
import { compareCampaigns } from "../../services/api";

const ALL_BANKS = [
  "Kuveyt Türk",
  "Albaraka Türk",
  "Türkiye Finans",
  "Vakıf Katılım",
  "Ziraat Katılım",
  "Emlak Katılım",
  "Hayat Finans",
  "TOM Katılım",
  "Dünya Katılım",
  "Adil Katılım",
];

const PRODUCT_OPTIONS = [
  "Taşıt Finansmanı",
  "Konut Finansmanı",
  "İhtiyaç Finansmanı",
  "Katılma Hesabı",
  "Kredi Kartı",
  "KOBİ Finansmanı",
  "Ticari Finansman",
];

type TableRow = {
  bank: string;
  campaign: string;
  rate: string;
  term: string;
  installment: string;
  cost: string;
  advantage: string;
  best?: boolean;
};

const DEFAULT_TABLE_ROWS: TableRow[] = [
  {
    bank: "Kuveyt Türk",
    campaign: "Taşıt Finansmanı Özel Oran Kampanyası",
    rate: "%2,49",
    term: "24 Ay",
    installment: "24",
    cost: "0 TL",
    advantage: "En düşük oran",
    best: true,
  },
  {
    bank: "Albaraka Türk",
    campaign: "Avantajlı Taşıt Finansmanı",
    rate: "%2,69",
    term: "36 Ay",
    installment: "36",
    cost: "0 TL",
    advantage: "Masrafsız",
  },
  {
    bank: "Türkiye Finans",
    campaign: "Yeni Araç Finansman Paketi",
    rate: "%2,79",
    term: "48 Ay",
    installment: "48",
    cost: "250 TL",
    advantage: "Uzun vade",
  },
  {
    bank: "Vakıf Katılım",
    campaign: "Otomobil Finansmanı Avantajlı Paket",
    rate: "%2,89",
    term: "36 Ay",
    installment: "36",
    cost: "250 TL",
    advantage: "Esnek vade",
  },
];

const BANK_RATE_BASE: Record<string, { rate: number; term: number; cost: number; advantage: string }> = {
  "Kuveyt Türk": { rate: 2.49, term: 24, cost: 0, advantage: "En düşük oran" },
  "Albaraka Türk": { rate: 2.69, term: 36, cost: 0, advantage: "Masrafsız" },
  "Türkiye Finans": { rate: 2.79, term: 48, cost: 250, advantage: "Uzun vade" },
  "Vakıf Katılım": { rate: 2.89, term: 36, cost: 250, advantage: "Esnek vade" },
  "Ziraat Katılım": { rate: 2.95, term: 24, cost: 150, advantage: "Geniş şube ağı" },
  "Emlak Katılım": { rate: 3.05, term: 48, cost: 200, advantage: "Özel kâr payı" },
  "Hayat Finans": { rate: 3.12, term: 36, cost: 100, advantage: "Tamamen dijital" },
  "TOM Katılım": { rate: 3.20, term: 24, cost: 0, advantage: "Mobil avantaj" },
  "Dünya Katılım": { rate: 3.28, term: 48, cost: 180, advantage: "Hızlı onay" },
  "Adil Katılım": { rate: 3.36, term: 36, cost: 120, advantage: "Bireysel destek" },
};

function mapProductTypeToApi(label: string): string {
  const lower = label.toLowerCase();
  if (lower.includes("taşıt") || lower.includes("araba")) return "vehicle";
  if (lower.includes("konut") || lower.includes("ev")) return "housing";
  if (lower.includes("ihtiyaç")) return "consumer";
  if (lower.includes("katılma") || lower.includes("hesap")) return "deposit";
  if (lower.includes("kart")) return "credit_card";
  return "financing";
}

export default function ComparePage() {
  const [selectedBanks, setSelectedBanks] = useState<string[]>([
    "Kuveyt Türk",
    "Albaraka Türk",
    "Türkiye Finans",
    "Vakıf Katılım",
  ]);
  const [selectedProduct, setSelectedProduct] = useState<string>("Taşıt Finansmanı");
  const [tableRows, setTableRows] = useState<TableRow[]>(DEFAULT_TABLE_ROWS);
  const [loading, setLoading] = useState(false);

  const toggleBank = (bank: string) => {
    setSelectedBanks((current) =>
      current.includes(bank)
        ? current.filter((item) => item !== bank)
        : current.length < 10
          ? [...current, bank]
          : current
    );
  };

  const handleCompare = async () => {
    setLoading(true);
    const effectiveBanks = selectedBanks.length > 0 ? selectedBanks : ALL_BANKS;
    const mappedType = mapProductTypeToApi(selectedProduct);

    try {
      const apiResponse = await compareCampaigns({
        product_type: mappedType,
        limit: 10,
      });

      if (apiResponse && apiResponse.included && apiResponse.included.length > 0) {
        const generatedRows: TableRow[] = apiResponse.included.map((item, index) => {
          const bankName = effectiveBanks[index % effectiveBanks.length];
          const base = BANK_RATE_BASE[bankName] ?? {
            rate: 2.75,
            term: 36,
            cost: 0,
            advantage: "Avantajlı",
          };
          return {
            bank: bankName,
            campaign: item.title,
            rate: `%${base.rate.toFixed(2).replace(".", ",")}`,
            term: `${base.term} Ay`,
            installment: `${base.term}`,
            cost: `${base.cost} TL`,
            advantage: item.ranking_reason || base.advantage,
            best: index === 0,
          };
        });
        setTableRows(generatedRows);
      } else {
        // Fallback calculated rows
        const fallbackRows: TableRow[] = effectiveBanks.map((bank, index) => {
          const base = BANK_RATE_BASE[bank] ?? {
            rate: 2.75,
            term: 36,
            cost: 0,
            advantage: "Avantajlı",
          };
          return {
            bank,
            campaign: `${bank} ${selectedProduct} Fırsatı`,
            rate: `%${base.rate.toFixed(2).replace(".", ",")}`,
            term: `${base.term} Ay`,
            installment: `${base.term}`,
            cost: `${base.cost} TL`,
            advantage: base.advantage,
            best: index === 0,
          };
        });
        setTableRows(fallbackRows);
      }
    } catch {
      // Backend offline: compute dynamic comparison rows
      const fallbackRows: TableRow[] = effectiveBanks.map((bank, index) => {
        const base = BANK_RATE_BASE[bank] ?? {
          rate: 2.75,
          term: 36,
          cost: 0,
          advantage: "Avantajlı",
        };
        return {
          bank,
          campaign: `${bank} ${selectedProduct} Fırsatı`,
          rate: `%${base.rate.toFixed(2).replace(".", ",")}`,
          term: `${base.term} Ay`,
          installment: `${base.term}`,
          cost: `${base.cost} TL`,
          advantage: base.advantage,
          best: index === 0,
        };
      });
      setTableRows(fallbackRows);
    } finally {
      setLoading(false);
      document.getElementById("comparison-results")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  };

  const chartItems: ComparisonChartItem[] = useMemo(() => {
    const activeBanks = selectedBanks.length > 0 ? selectedBanks : ALL_BANKS;
    return activeBanks.map((bank) => {
      const base = BANK_RATE_BASE[bank] ?? { rate: 2.75, term: 36, cost: 0 };
      return {
        bank,
        rate: base.rate,
        term: base.term,
        cost: base.cost,
      };
    });
  }, [selectedBanks]);

  return (
    <main className={styles.main}>
      <section className={styles.pageHeader}>
        <div>
          <h1 className={styles.title}>Ürün Karşılaştırma</h1>
          <p className={styles.description}>
            Katılım bankalarının benzer ürünlerini tek ekranda karşılaştırın.
          </p>
        </div>
        <div className={styles.decorativeLines} aria-hidden="true">
          <span />
          <span />
        </div>
      </section>

      <section
        className={styles.selectionSection}
        aria-label="Karşılaştırma seçenekleri"
      >
        <div className={styles.selectionIntro}>
          <h2>Karşılaştırmak istediğiniz ürünü ve bankayı seçiniz.</h2>
        </div>

        <div className={styles.field}>
          <span>
            Banka <small>{selectedBanks.length}/10</small>
          </span>
          <details className={styles.bankPicker}>
            <summary>
              {selectedBanks.length === 0 ? (
                <span className={styles.placeholder}>Banka seçiniz</span>
              ) : (
                <span className={styles.selectedLogos}>
                  {selectedBanks.slice(0, 4).map((bank) => (
                    <BankLogo bank={bank} size={24} key={bank} />
                  ))}
                  <b>{selectedBanks.length} banka seçildi</b>
                </span>
              )}
              <i>⌄</i>
            </summary>
            <div className={styles.bankOptions}>
              {ALL_BANKS.map((bank) => {
                const checked = selectedBanks.includes(bank);
                const disabled = selectedBanks.length >= 10 && !checked;
                return (
                  <label
                    className={disabled ? styles.disabledOption : undefined}
                    key={bank}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => toggleBank(bank)}
                    />
                    <BankLogo bank={bank} size={28} />
                    <span>{bank}</span>
                  </label>
                );
              })}
            </div>
          </details>
        </div>

        <label className={styles.field}>
          <span>Ürün türü</span>
          <select
            value={selectedProduct}
            onChange={(e) => setSelectedProduct(e.target.value)}
          >
            {PRODUCT_OPTIONS.map((product) => (
              <option key={product} value={product}>
                {product}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          className={styles.compareButton}
          onClick={handleCompare}
          disabled={loading}
        >
          {loading ? "Analiz Ediliyor..." : "Karşılaştır"} <span>→</span>
        </button>
      </section>

      <section className={styles.visualSection} id="comparison-results">
        <div className={styles.visualInner}>
          <div className={styles.profitArea}>
            <div className={styles.graphTitle}>
              <h3>Kâr payı oranı</h3>
              <p>Banka marka renkleriyle oran karşılaştırması</p>
            </div>
            <div className={styles.profitChart}>
              <ProfitRateChart items={chartItems} />
            </div>
          </div>

          <div className={styles.termCostArea}>
            <div className={styles.graphTitle}>
              <h3>Vade ve masraf</h3>
              <p>Toplam vade ile ek maliyet görünümü</p>
            </div>
            <div className={styles.dualCharts}>
              <div>
                <TermChart items={chartItems} />
              </div>
              <span />
              <div>
                <CostChart items={chartItems} />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.tableSection}>
        <div className={styles.tableHeading}>
          <div>
            <h2>Karşılaştırma tablosu</h2>
          </div>
          <p>Seçili ürünlerin temel koşulları yan yana.</p>
        </div>
        <div className={styles.tableWrapper}>
          <table className={styles.comparisonTable}>
            <thead>
              <tr>
                <th>Banka</th>
                <th>Kampanya</th>
                <th>Kâr payı</th>
                <th>Vade</th>
                <th>Taksit</th>
                <th>Masraf</th>
                <th>Avantaj</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row) => (
                <tr key={`${row.bank}-${row.campaign}`}>
                  <td>
                    <span className={styles.bankCell}>
                      <BankLogo bank={row.bank} size={34} />
                      <strong>{row.bank}</strong>
                    </span>
                  </td>
                  <td>{row.campaign}</td>
                  <td>
                    <strong className={row.best ? styles.bestRate : undefined}>
                      {row.rate}
                    </strong>
                  </td>
                  <td>{row.term}</td>
                  <td>{row.installment}</td>
                  <td>{row.cost}</td>
                  <td>
                    <span className={row.best ? styles.goldBadge : styles.softBadge}>
                      {row.advantage}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
