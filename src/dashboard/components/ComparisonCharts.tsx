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
];

export function ProfitRateChart() {
  return (
    <Plot
      data={[
        {
          type: "bar",
          x: banks,
          y: [2.49, 2.69, 2.79, 2.89],
          marker: {
            color: ["#12B8B0", "#E7AA2D", "#12B8B0", "#002B3A"],
          },
          text: ["%2,49", "%2,69", "%2,79", "%2,89"],
          textposition: "outside",
          hovertemplate: "%{x}: %{y}%<extra></extra>",
        },
      ]}
      layout={{
        autosize: true,
        margin: { l: 45, r: 20, t: 20, b: 70 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: false,
        yaxis: {
          range: [0, 4],
          gridcolor: "#E3E9EB",
          zerolinecolor: "#E3E9EB",
        },
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
          y: [24, 36, 48, 36],
          marker: {
            color: "#12B8B0",
          },
          text: ["24", "36", "48", "36"],
          textposition: "outside",
          hovertemplate: "%{x}: %{y} Ay<extra></extra>",
        },
      ]}
      layout={{
        autosize: true,
        margin: { l: 40, r: 10, t: 30, b: 65 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: false,
        title: {
          text: "Vade (Ay)",
          font: {
            color: "#12B8B0",
            size: 15,
          },
        },
        yaxis: {
          range: [0, 60],
          gridcolor: "#E3E9EB",
          zerolinecolor: "#E3E9EB",
        },
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
          y: [0, 0, 250, 250],
          marker: {
            color: "#E7AA2D",
          },
          text: ["0", "0", "250", "250"],
          textposition: "outside",
          hovertemplate: "%{x}: %{y} TL<extra></extra>",
        },
      ]}
      layout={{
        autosize: true,
        margin: { l: 45, r: 10, t: 30, b: 65 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: false,
        title: {
          text: "Masraf (TL)",
          font: {
            color: "#E7AA2D",
            size: 15,
          },
        },
        yaxis: {
          range: [0, 600],
          gridcolor: "#E3E9EB",
          zerolinecolor: "#E3E9EB",
        },
      }}
      config={{
        displayModeBar: false,
        responsive: true,
      }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}