"use client";

import dynamic from "next/dynamic";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
});

const banks = [
  "Kuveyt Türk",
  "Albaraka Türk",
  "Türkiye Finans",
  "Vakıf Katılım",
  "Ziraat Katılım",
];

const values = [52, 34, 24, 11, 7];

export default function CampaignDistributionChart() {
  return (
    <Plot
      data={[
        {
          type: "pie",
          labels: banks,
          values,
          hole: 0.55,
          textinfo: "none",
          hovertemplate: "%{label}: %{value} kampanya<extra></extra>",
          marker: {
            colors: [
              "#002B3A",
              "#12B8B0",
              "#E7AA2D",
              "#00AFA8",
              "#9CE5E1",
            ],
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