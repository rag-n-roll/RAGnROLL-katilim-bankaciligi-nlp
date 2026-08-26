"use client";

import { useMemo, useState } from "react";
import BankLogo from "../../components/BankLogo";
import styles from "./page.module.css";
import { parseCampaignText } from "./textFormatter";

export type CampaignRowItem = {
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

const getBadgeClass = (type: string) => {
  if (type === "Kart") return styles.cardBadge;
  if (type === "Yatırım") return styles.investmentBadge;
  return styles.financeBadge;
};

function CampaignFormattedContent({ text }: { text: string }) {
  const blocks = useMemo(() => parseCampaignText(text), [text]);

  if (blocks.length === 0) {
    return <p className={styles.formattedParagraph}>Metin bulunmuyor.</p>;
  }

  return (
    <>
      {blocks.map((block, idx) => {
        if (block.type === "heading") {
          return (
            <h4 key={idx} className={styles.sectionHeading}>
              {block.text}
            </h4>
          );
        }
        if (block.type === "list") {
          if (block.ordered) {
            return (
              <ol key={idx} className={styles.numberedList}>
                {block.items.map((item, itemIdx) => (
                  <li key={itemIdx}>{item}</li>
                ))}
              </ol>
            );
          }
          return (
            <ul key={idx} className={styles.bulletList}>
              {block.items.map((item, itemIdx) => (
                <li key={itemIdx}>{item}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={idx} className={styles.formattedParagraph}>
            {block.text}
          </p>
        );
      })}
    </>
  );
};

export default function CampaignExplorer({ rows }: { rows: CampaignRowItem[] }) {
  const [selectedId, setSelectedId] = useState<string>(rows[0]?.id ?? "");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedType, setSelectedType] = useState<string>("all");

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      const matchesSearch =
        !searchQuery ||
        row.bank.toLowerCase().includes(searchQuery.toLowerCase()) ||
        row.campaign.toLowerCase().includes(searchQuery.toLowerCase()) ||
        row.text.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesType =
        selectedType === "all" || row.type.toLowerCase() === selectedType.toLowerCase();

      return matchesSearch && matchesType;
    });
  }, [rows, searchQuery, selectedType]);

  const selected = useMemo(() => {
    const found = rows.find((r) => r.id === selectedId);
    return found ?? filteredRows[0] ?? rows[0];
  }, [rows, selectedId, filteredRows]);

  if (!selected && rows.length === 0) {
    return (
      <div style={{ padding: "40px 20px", textAlign: "center" }}>
        <p>Henüz kampanya verisi bulunamadı.</p>
      </div>
    );
  }

  return (
    <>
      <div
        style={{
          width: "min(1440px, calc(100% - 96px))",
          margin: "0 auto 16px",
          display: "flex",
          gap: "12px",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", gap: "8px", flex: 1, minWidth: "260px" }}>
          <input
            type="text"
            placeholder="Kampanya veya banka ara..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              flex: 1,
              padding: "9px 14px",
              borderRadius: "8px",
              border: "1px solid #d0ded8",
              fontSize: "14px",
              outline: "none",
            }}
          />
        </div>

        <div style={{ display: "flex", gap: "6px" }}>
          {["all", "Finansman", "Kart", "Yatırım"].map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setSelectedType(type)}
              style={{
                padding: "8px 14px",
                borderRadius: "8px",
                border: "1px solid",
                borderColor: selectedType === type ? "#075244" : "#d0ded8",
                background: selectedType === type ? "#075244" : "#ffffff",
                color: selectedType === type ? "#ffffff" : "#17313a",
                fontWeight: 600,
                fontSize: "13px",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
            >
              {type === "all" ? "Tümü" : type}
            </button>
          ))}
        </div>
      </div>

      <section className={styles.campaignWorkspace}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Tüm Kampanyalar</h2>
            <span className={styles.campaignCount}>{filteredRows.length} kampanya</span>
          </div>
          <div className={styles.campaignList}>
            {filteredRows.map((campaign) => (
              <button
                key={campaign.id}
                type="button"
                onClick={() => setSelectedId(campaign.id)}
                className={`${styles.campaignRow} ${
                  selected?.id === campaign.id ? styles.selectedCampaign : ""
                }`}
              >
                <BankLogo bank={campaign.bank} size={34} />
                <span className={styles.campaignInfo}>
                  <strong>{campaign.bank}</strong>
                  <span>{campaign.campaign}</span>
                </span>
                <span className={`${styles.typeBadge} ${getBadgeClass(campaign.type)}`}>
                  {campaign.type}
                </span>
              </button>
            ))}
          </div>
        </article>

        <div className={styles.detailColumn}>
          <article className={styles.panel}>
            <div className={styles.contentTitle}>
              <span className={styles.titleIcon}>▤</span>
              <h2>Kampanya Metni</h2>
            </div>
            {selected && (
              <>
                <div className={styles.selectedCampaignHeading}>
                  <BankLogo bank={selected.bank} size={34} />
                  <div>
                    <strong>{selected.bank}</strong>
                    <span>{selected.campaign}</span>
                  </div>
                </div>
                <div className={styles.campaignText}>
                  <section className={styles.summaryBlock}>
                    <h3>Kısa Özet</h3>
                    <CampaignFormattedContent text={selected.summary} />
                  </section>
                  <section className={styles.fullTextBlock}>
                    <h3>Kampanya Metni</h3>
                    <CampaignFormattedContent text={selected.cleanText} />
                  </section>
                </div>
                <div className={styles.aiNotice}>
                  <span>ⓘ</span>
                  Bu metin yapay zeka ile analiz edilerek finansal bilgiler çıkarılmıştır.
                </div>
              </>
            )}
          </article>

          <article className={styles.panel}>
            <div className={styles.contentTitle}>
              <span className={styles.titleIcon}>✣</span>
              <h2>Çıkarılan Bilgiler</h2>
            </div>
            {selected && (
              <div className={styles.extractedList}>
                {[
                  ["🏦", "Banka", selected.bank],
                  ["▣", "Ürün Türü", selected.type],
                  ["%", "Kâr Payı", selected.rate],
                  ["◷", "Vade", selected.term],
                  ["◉", "Masraf", selected.cost],
                  ["▦", "Geçerlilik Tarihi", selected.validity],
                ].map(([icon, label, value], index) => (
                  <div className={styles.extractedRow} key={label}>
                    <span className={styles.extractedLabel}>
                      <i className={`${styles.infoIcon} ${styles[`infoIcon${index % 3}`]}`}>
                        {icon}
                      </i>
                      {label}
                    </span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
            )}
          </article>
        </div>
      </section>

      <section className={styles.tableCard} id="all-campaigns">
        <h2>
          Yapılandırılmış Veri Tablosu{" "}
          <span className={styles.campaignCount}>{filteredRows.length} kayıt</span>
        </h2>
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
              {filteredRows.map((row) => (
                <tr
                  key={row.id}
                  className={selected?.id === row.id ? styles.selectedTableRow : undefined}
                  onClick={() => setSelectedId(row.id)}
                >
                  <td>
                    <div className={styles.tableBank}>
                      <BankLogo bank={row.bank} size={30} />
                      <strong>{row.bank}</strong>
                    </div>
                  </td>
                  <td className={styles.campaignCell}>
                    <button
                      type="button"
                      className={styles.campaignSelect}
                      onClick={() => setSelectedId(row.id)}
                    >
                      {row.campaign}
                    </button>
                  </td>
                  <td>
                    <span className={`${styles.typeBadge} ${getBadgeClass(row.type)}`}>
                      {row.type}
                    </span>
                  </td>
                  <td>
                    <strong>{row.rate}</strong>
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
    </>
  );
}
