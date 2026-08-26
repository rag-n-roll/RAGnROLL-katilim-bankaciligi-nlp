"use client";

import dynamic from "next/dynamic";
import { getBankBrandColor } from "./bankBrand";

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

const DEFAULT_VALUES = [69, 48, 13, 3, 208, 64, 10, 10, 45, 1];

export type DistributionItem = {
  name: string;
  count: number;
};

export default function CampaignDistributionChart({
  items,
  total,
}: {
  items?: DistributionItem[];
  total?: number;
}) {
  const banks = items && items.length > 0 ? items.map((i) => i.name) : DEFAULT_BANKS;
  const values = items && items.length > 0 ? items.map((i) => i.count) : DEFAULT_VALUES;
  const totalCampaigns =
    typeof total === "number"
      ? total
      : values.reduce((sum, v) => sum + v, 0);

  return (
    <Plot
      data={[
        {
          type: "pie",
          labels: banks,
          values,
          hole: 0.66,
          textinfo: "none",
          hovertemplate: "%{label}: %{value} kampanya<extra></extra>",
          marker: {
            colors: banks.map(getBankBrandColor),
          },
        },
      ]}
      layout={{
        autosize: true,
        margin: {
          l: 10,
          r: 10,
          t: 10,
          b: 10,
        },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: false,
        annotations: [
          {
            text: `<b>${totalCampaigns}</b><br><span style='font-size:11px;color:#62737B'>kampanya</span>`,
            x: 0.5,
            y: 0.5,
            xref: "paper",
            yref: "paper",
            showarrow: false,
            font: { color: "#102F3D", size: 23 },
          },
        ],
      }}
      config={{
        displayModeBar: false,
        responsive: true,
      }}
      style={{
        width: "100%",
        height: "100%",
      }}
    />
  );
}
