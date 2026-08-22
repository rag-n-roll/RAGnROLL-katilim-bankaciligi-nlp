"use client";

import { useState } from "react";
import BankLogo from "../../components/BankLogo";
import styles from "./page.module.css";

type Row = {
  id: string;
  bank: string;
  campaign: string;
  text: string;
  summary: string;
  cleanText: string;
  type: string;
  rate: string;
  term: string;
  cost: string;
  validity: string;
};

const badgeClass = (type: string) =>
  type === "Kart" ? styles.cardBadge : type === "Yatırım" ? styles.investmentBadge : styles.financeBadge;

export default function CampaignExplorer({ rows }: { rows: Row[] }) {
  const [selected, setSelected] = useState<Row>(rows[0]);

  return (
    <>
      <section className={styles.campaignWorkspace}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Tüm Kampanyalar</h2>
            <span className={styles.campaignCount}>{rows.length} kampanya</span>
          </div>
          <div className={styles.campaignList}>
            {rows.map((campaign) => (
              <button key={campaign.id} type="button" onClick={() => setSelected(campaign)}
                className={`${styles.campaignRow} ${selected.id === campaign.id ? styles.selectedCampaign : ""}`}>
                <BankLogo bank={campaign.bank} size={34} />
                <span className={styles.campaignInfo}>
                  <strong>{campaign.bank}</strong><span>{campaign.campaign}</span>
                </span>
                <span className={`${styles.typeBadge} ${badgeClass(campaign.type)}`}>{campaign.type}</span>
              </button>
            ))}
          </div>
        </article>

        <div className={styles.detailColumn}>
        <article className={styles.panel}>
          <div className={styles.contentTitle}><span className={styles.titleIcon}>▤</span><h2>Kampanya Metni</h2></div>
          <div className={styles.selectedCampaignHeading}>
            <BankLogo bank={selected.bank} size={34} />
            <div><strong>{selected.bank}</strong><span>{selected.campaign}</span></div>
          </div>
          <div className={styles.campaignText}>
            <section className={styles.summaryBlock}>
              <h3>Kısa Özet</h3>
              <p>{selected.summary}</p>
            </section>
            <section className={styles.fullTextBlock}>
              <h3>Kampanya Metni</h3>
              <p>{selected.cleanText}</p>
            </section>
          </div>
          <div className={styles.aiNotice}><span>ⓘ</span>Bu metin yapay zeka ile analiz edilerek finansal bilgiler çıkarılmıştır.</div>
        </article>

        <article className={styles.panel}>
          <div className={styles.contentTitle}><span className={styles.titleIcon}>✣</span><h2>Çıkarılan Bilgiler</h2></div>
          <div className={styles.extractedList}>
            {[['🏦', 'Banka', selected.bank], ['▣', 'Ürün Türü', selected.type], ['%', 'Kâr Payı', selected.rate], ['◷', 'Vade', selected.term], ['◉', 'Masraf', selected.cost], ['▦', 'Geçerlilik Tarihi', selected.validity]].map(([icon, label, value], index) => (
              <div className={styles.extractedRow} key={label}>
                <span className={styles.extractedLabel}><i className={`${styles.infoIcon} ${styles[`infoIcon${index % 3}`]}`}>{icon}</i>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </article>
        </div>
      </section>

      <section className={styles.tableCard} id="all-campaigns">
        <h2>Yapılandırılmış Veri Tablosu <span className={styles.campaignCount}>{rows.length} kayıt</span></h2>
        <div className={styles.tableWrapper}><table className={styles.dataTable}>
          <thead><tr><th>Banka</th><th>Kampanya Adı</th><th>Tür</th><th>Kâr Payı</th><th>Vade</th><th>Masraf</th><th>Geçerlilik</th></tr></thead>
          <tbody>{rows.map((row) => (
            <tr key={row.id} className={selected.id === row.id ? styles.selectedTableRow : undefined} onClick={() => setSelected(row)}>
              <td><div className={styles.tableBank}><BankLogo bank={row.bank} size={30} /><strong>{row.bank}</strong></div></td>
              <td className={styles.campaignCell}><button type="button" className={styles.campaignSelect} onClick={() => setSelected(row)}>{row.campaign}</button></td>
              <td><span className={`${styles.typeBadge} ${badgeClass(row.type)}`}>{row.type}</span></td>
              <td><strong>{row.rate}</strong></td><td>{row.term}</td><td>{row.cost}</td><td>{row.validity}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </section>
    </>
  );
}
