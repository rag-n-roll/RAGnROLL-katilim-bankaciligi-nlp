"use client";

import dynamic from "next/dynamic";
import { getBankBrand, getBankBrandColor } from "./bankBrand";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
});

const DEFAULT_BANKS = [
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

const DEFAULT_PROFIT_RATES = [2.49, 2.69, 2.79, 2.89, 2.95, 3.05, 3.12, 3.2, 3.28, 3.36];
const DEFAULT_TERMS = [24, 36, 48, 36, 24, 48, 36, 24, 48, 36];
const DEFAULT_COSTS = [0, 0, 250, 250, 150, 200, 100, 0, 180, 120];

export type ComparisonChartItem = {
  bank: string;
  rate?: number | null;
  term?: number | null;
  cost?: number | null;
};

const makeBankTickText = (bankList: string[]) =>
  bankList.map((bank) => {
    const [first, ...rest] = bank.split(" ");
    return `<b>${first}<br>${rest.join(" ")}</b>`;
  });

const makeBankLogoImages = (
  bankList: string[],
  values: number[],
  sizeY: number,
  offsetY: number,
  minimumY = 0
) =>
  bankList.map((bank, index) => ({
    source: `/bank-logos/${getBankBrand(bank)?.file ?? "kuveyt-turk.png"}`,
    xref: "x" as const,
    yref: "y" as const,
    x: bank,
    y: Math.max((values[index] ?? 0) + offsetY, minimumY),
    sizex: 0.66,
    sizey: sizeY,
    xanchor: "center" as const,
    yanchor: "middle" as const,
    layer: "above" as const,
  }));

export function ProfitRateChart({ items }: { items?: ComparisonChartItem[] }) {
  const banks = items && items.length > 0 ? items.map((i) => i.bank) : DEFAULT_BANKS;
  const rates =
    items && items.length > 0
      ? items.map((i) => (typeof i.rate === "number" && !isNaN(i.rate) ? i.rate : 2.5))
      : DEFAULT_PROFIT_RATES;
  const tickText = makeBankTickText(banks);
  const maxRate = Math.max(4, ...rates.map((r) => r + 0.8));

  return (
    <Plot
      data={[
        {
          type: "bar",
          x: banks,
          y: rates,
          marker: {
            color: banks.map(getBankBrandColor),
          },
          text: rates.map((value) => `%${String(value).replace(".", ",")}`),
          textposition: "inside",
          insidetextanchor: "middle",
          textfont: { color: "#052F2B", size: 14, family: "Arial Black, Arial, sans-serif" },
          hovertemplate: "%{x}: %{y}%<extra></extra>",
        },
      ]}
      layout={{
        autosize: true,
        margin: { l: 45, r: 20, t: 20, b: 125 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: false,
        yaxis: {
          range: [0, maxRate],
          gridcolor: "#DDE3E7",
          zerolinecolor: "#DDE3E7",
        },
        xaxis: {
          tickvals: banks,
          ticktext: tickText,
          tickfont: { color: "#082F2B", size: 13 },
          tickangle: 0,
          automargin: true,
        },
        images: makeBankLogoImages(banks, rates, 0.4, 0.34),
      }}
      config={{
        displayModeBar: false,
        responsive: true,
      }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}

export function TermChart({ items }: { items?: ComparisonChartItem[] }) {
  const banks = items && items.length > 0 ? items.map((i) => i.bank) : DEFAULT_BANKS;
  const terms =
    items && items.length > 0
      ? items.map((i) => (typeof i.term === "number" && !isNaN(i.term) ? i.term : 24))
      : DEFAULT_TERMS;
  const tickText = makeBankTickText(banks);
  const maxTerm = Math.max(60, ...terms.map((t) => t + 12));

  return (
    <Plot
      data={[
        {
          type: "bar",
          x: banks,
          y: terms,
          marker: {
            color: banks.map(getBankBrandColor),
          },
          text: terms.map(String),
          textposition: "inside",
          insidetextanchor: "middle",
          textfont: { color: "#052F2B", size: 13, family: "Arial Black, Arial, sans-serif" },
          hovertemplate: "%{x}: %{y} Ay<extra></extra>",
        },
      ]}
      layout={{
        autosize: true,
        margin: { l: 40, r: 10, t: 30, b: 120 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: false,
        title: {
          text: "Vade (Ay)",
          font: {
            color: "#6E879B",
            size: 15,
          },
        },
        yaxis: {
          range: [0, maxTerm],
          gridcolor: "#DDE3E7",
          zerolinecolor: "#DDE3E7",
        },
        xaxis: {
          tickvals: banks,
          ticktext: tickText,
          tickfont: { color: "#082F2B", size: 12 },
          tickangle: 0,
          automargin: true,
        },
        images: makeBankLogoImages(banks, terms, 6.5, 7),
      }}
      config={{
        displayModeBar: false,
        responsive: true,
      }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}

export function CostChart({ items }: { items?: ComparisonChartItem[] }) {
  const banks = items && items.length > 0 ? items.map((i) => i.bank) : DEFAULT_BANKS;
  const costs =
    items && items.length > 0
      ? items.map((i) => (typeof i.cost === "number" && !isNaN(i.cost) ? i.cost : 0))
      : DEFAULT_COSTS;
  const tickText = makeBankTickText(banks);
  const maxCost = Math.max(600, ...costs.map((c) => c + 100));

  return (
    <Plot
      data={[
        {
          type: "bar",
          x: banks,
          y: costs,
          marker: {
            color: banks.map(getBankBrandColor),
          },
          text: costs.map(String),
          textposition: "inside",
          insidetextanchor: "middle",
          textfont: { color: "#052F2B", size: 13, family: "Arial Black, Arial, sans-serif" },
          hovertemplate: "%{x}: %{y} TL<extra></extra>",
        },
      ]}
      layout={{
        autosize: true,
        margin: { l: 45, r: 10, t: 30, b: 120 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: false,
        title: {
          text: "Masraf (TL)",
          font: {
            color: "#E8B84A",
            size: 15,
          },
        },
        yaxis: {
          range: [0, maxCost],
          gridcolor: "#DDE3E7",
          zerolinecolor: "#DDE3E7",
        },
        xaxis: {
          tickvals: banks,
          ticktext: tickText,
          tickfont: { color: "#082F2B", size: 12 },
          tickangle: 0,
          automargin: true,
        },
        images: makeBankLogoImages(banks, costs, 54, 60, 48),
      }}
      config={{
        displayModeBar: false,
        responsive: true,
      }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}
