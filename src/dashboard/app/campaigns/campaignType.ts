export type CampaignDisplayType = "Finansman" | "Kart" | "Yatırım" | "Belirsiz";

export function mapCampaignType(value?: string | null): CampaignDisplayType {
  switch (value?.trim().toLocaleLowerCase("tr-TR")) {
    case "financing":
      return "Finansman";
    case "card":
      return "Kart";
    case "investment":
      return "Yatırım";
    default:
      return "Belirsiz";
  }
}
