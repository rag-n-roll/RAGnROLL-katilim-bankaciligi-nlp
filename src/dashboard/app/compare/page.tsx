"use client";

import { useState } from "react";
import styles from "./page.module.css";
import { ProfitRateChart, TermChart, CostChart } from "../../components/ComparisonCharts";
import BankLogo from "../../components/BankLogo";

const bankOptions = ["Kuveyt Türk", "Albaraka Türk", "Türkiye Finans", "Vakıf Katılım", "Ziraat Katılım", "Emlak Katılım", "Hayat Finans", "TOM Katılım", "Dünya Katılım", "Adil Katılım"];
const productOptions = ["Taşıt Finansmanı", "Konut Finansmanı", "İhtiyaç Finansmanı", "Katılma Hesabı", "Kredi Kartı", "KOBİ Finansmanı", "Ticari Finansman"];
const comparisonRows = [
  { bank: "Kuveyt Türk", campaign: "Taşıt Finansmanı Özel Oran Kampanyası", rate: "%2,49", term: "24 Ay", installment: "24", cost: "0 TL", advantage: "En düşük oran", best: true },
  { bank: "Albaraka Türk", campaign: "Avantajlı Taşıt Finansmanı", rate: "%2,69", term: "36 Ay", installment: "36", cost: "0 TL", advantage: "Masrafsız" },
  { bank: "Türkiye Finans", campaign: "Yeni Araç Finansman Paketi", rate: "%2,79", term: "48 Ay", installment: "48", cost: "250 TL", advantage: "Uzun vade" },
  { bank: "Vakıf Katılım", campaign: "Otomobil Finansmanı Avantajlı Paket", rate: "%2,89", term: "36 Ay", installment: "36", cost: "250 TL", advantage: "Esnek vade" },
];

export default function ComparePage() {
  const [selectedBanks, setSelectedBanks] = useState<string[]>([]);
  const toggleBank = (bank: string) => {
    setSelectedBanks(current => current.includes(bank) ? current.filter(item => item !== bank) : current.length < 10 ? [...current, bank] : current);
  };

  return <main className={styles.main}>
    <section className={styles.pageHeader}>
      <div><h1 className={styles.title}>Ürün Karşılaştırma</h1><p className={styles.description}>Katılım bankalarının benzer ürünlerini tek ekranda karşılaştırın.</p></div>
      <div className={styles.decorativeLines} aria-hidden="true"><span /><span /></div>
    </section>

    <section className={styles.selectionSection} aria-label="Karşılaştırma seçenekleri">
      <div className={styles.selectionIntro}><h2>Karşılaştırmak istediğiniz ürünü ve bankayı seçiniz.</h2></div>
      <div className={styles.field}>
        <span>Banka <small>{selectedBanks.length}/10</small></span>
        <details className={styles.bankPicker}>
          <summary>
            {selectedBanks.length === 0 ? <span className={styles.placeholder}>Banka seçiniz</span> : <span className={styles.selectedLogos}>{selectedBanks.map(bank => <BankLogo bank={bank} size={24} key={bank} />)}<b>{selectedBanks.length} banka seçildi</b></span>}
            <i>⌄</i>
          </summary>
          <div className={styles.bankOptions}>
            {bankOptions.map(bank => {
              const checked = selectedBanks.includes(bank);
              const disabled = selectedBanks.length >= 10 && !checked;
              return <label className={disabled ? styles.disabledOption : undefined} key={bank}>
                <input type="checkbox" checked={checked} disabled={disabled} onChange={() => toggleBank(bank)} />
                <BankLogo bank={bank} size={28} /><span>{bank}</span>
              </label>;
            })}
          </div>
        </details>
      </div>
      <label className={styles.field}><span>Ürün türü</span><select defaultValue=""><option value="" disabled>Ürün türü seçiniz</option>{productOptions.map(product => <option key={product}>{product}</option>)}</select></label>
      <button type="button" className={styles.compareButton} onClick={() => document.getElementById("comparison-results")?.scrollIntoView({ behavior: "smooth", block: "start" })}>Karşılaştır <span>→</span></button>
    </section>

    <section className={styles.visualSection} id="comparison-results"><div className={styles.visualInner}>
      <div className={styles.profitArea}><div className={styles.graphTitle}><h3>Kâr payı oranı</h3><p>Banka marka renkleriyle oran karşılaştırması</p></div><div className={styles.profitChart}><ProfitRateChart /></div></div>
      <div className={styles.termCostArea}><div className={styles.graphTitle}><h3>Vade ve masraf</h3><p>Toplam vade ile ek maliyet görünümü</p></div><div className={styles.dualCharts}><div><TermChart /></div><span /><div><CostChart /></div></div></div>
    </div></section>

    <section className={styles.tableSection}>
      <div className={styles.tableHeading}><div><h2>Karşılaştırma tablosu</h2></div><p>Seçili ürünlerin temel koşulları yan yana.</p></div>
      <div className={styles.tableWrapper}><table className={styles.comparisonTable}>
        <thead><tr><th>Banka</th><th>Kampanya</th><th>Kâr payı</th><th>Vade</th><th>Taksit</th><th>Masraf</th><th>Avantaj</th></tr></thead>
        <tbody>{comparisonRows.map(row => <tr key={row.bank}>
          <td><span className={styles.bankCell}><BankLogo bank={row.bank} size={34} /><strong>{row.bank}</strong></span></td><td>{row.campaign}</td>
          <td><strong className={row.best ? styles.bestRate : undefined}>{row.rate}</strong></td><td>{row.term}</td><td>{row.installment}</td><td>{row.cost}</td>
          <td><span className={row.best ? styles.goldBadge : styles.softBadge}>{row.advantage}</span></td>
        </tr>)}</tbody>
      </table></div>
    </section>
  </main>;
}
