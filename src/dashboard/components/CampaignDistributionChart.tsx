"use client";

import dynamic from "next/dynamic";
import { getBankBrandColor } from "./bankBrand";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
});

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
  if (!items?.length) return null;

  const banks = items.map((item) => item.name);
  const values = items.map((item) => item.count);
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
