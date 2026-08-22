export const bankBrands = [
  { names: ["kuveyt türk", "kuveyt turk"], file: "kuveyt-turk.png", color: "#009879" },
  { names: ["albaraka türk", "albaraka turk", "albaraka"], file: "albaraka-turk.png", color: "#ef7d22" },
  { names: ["türkiye finans", "turkiye finans"], file: "turkiye-finans.png", color: "#39C9BF" },
  { names: ["vakıf katılım", "vakif katilim"], file: "vakif-katilim.png", color: "#6598C8" },
  { names: ["ziraat katılım", "ziraat katilim"], file: "ziraat-katilim.png", color: "#ed1c24" },
  { names: ["emlak katılım", "emlak katilim"], file: "emlak-katilim.png", color: "#159447" },
  { names: ["hayat finans"], file: "hayat-finans.ico", color: "#6e3fa3" },
  { names: ["tom katılım", "tom katilim", "tom bank", "t.o.m."], file: "tom-katilim.png", color: "#7438d6" },
  { names: ["dünya katılım", "dunya katilim"], file: "dunya-katilim.png", color: "#83B7E8" },
  { names: ["adil katılım", "adil katilim"], file: "adil-katilim.png", color: "#00a7a0" },
] as const;

export function getBankBrand(bank: string) {
  const normalizedBank = bank.toLocaleLowerCase("tr-TR");
  return bankBrands.find(({ names }) => names.some((name) => normalizedBank.includes(name)));
}

export function getBankBrandColor(bank: string) {
  return getBankBrand(bank)?.color ?? "#476a86";
}
