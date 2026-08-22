"use client";

import dynamic from "next/dynamic";
import { getBankBrand, getBankBrandColor } from "./bankBrand";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
});

const banks = [
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

const profitRates = [2.49, 2.69, 2.79, 2.89, 2.95, 3.05, 3.12, 3.2, 3.28, 3.36];
const terms = [24, 36, 48, 36, 24, 48, 36, 24, 48, 36];
const costs = [0, 0, 250, 250, 150, 200, 100, 0, 180, 120];
const bankTickText = banks.map(bank => {
  const [first, ...rest] = bank.split(" ");
  return `<b>${first}<br>${rest.join(" ")}</b>`;
});
const makeBankLogoImages = (values: number[], sizeY: number, offsetY: number, minimumY = 0) => banks.map((bank, index) => ({
  source: `/bank-logos/${getBankBrand(bank)?.file}`,
  xref: "x" as const,
  yref: "y" as const,
  x: bank,
  y: Math.max(values[index] + offsetY, minimumY),
  sizex: 0.66,
  sizey: sizeY,
  xanchor: "center" as const,
  yanchor: "middle" as const,
  layer: "above" as const,
}));

export function ProfitRateChart() {
  return (
    <Plot
      data={[
        {
          type: "bar",
          x: banks,
          y: profitRates,
          marker: {
            color: banks.map(getBankBrandColor),
          },
          text: profitRates.map(value => `%${String(value).replace(".", ",")}`),
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
          range: [0, 4],
          gridcolor: "#DDE3E7",
          zerolinecolor: "#DDE3E7",
        },
        xaxis: { tickvals: banks, ticktext: bankTickText, tickfont: { color: "#082F2B", size: 13 }, tickangle: 0, automargin: true },
        images: makeBankLogoImages(profitRates, 0.4, 0.34),
      }}
      config={{
        displayModeBar: false,
        responsive: true,
      }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}

export function TermChart() {
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
          range: [0, 60],
          gridcolor: "#DDE3E7",
          zerolinecolor: "#DDE3E7",
        },
        xaxis: { tickvals: banks, ticktext: bankTickText, tickfont: { color: "#082F2B", size: 12 }, tickangle: 0, automargin: true },
        images: makeBankLogoImages(terms, 6.5, 7),
      }}
      config={{
        displayModeBar: false,
        responsive: true,
      }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}

export function CostChart() {
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
          range: [0, 600],
          gridcolor: "#DDE3E7",
          zerolinecolor: "#DDE3E7",
        },
        xaxis: { tickvals: banks, ticktext: bankTickText, tickfont: { color: "#082F2B", size: 12 }, tickangle: 0, automargin: true },
        images: makeBankLogoImages(costs, 54, 60, 48),
      }}
      config={{
        displayModeBar: false,
        responsive: true,
      }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}
