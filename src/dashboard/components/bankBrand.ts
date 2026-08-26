export type BankBrand = {
  names: readonly string[];
  file: string;
  color: string;
  imageWidth: number;
  imageHeight: number;
};

export const bankBrands: readonly BankBrand[] = [
  { names: ["kuveyt türk", "kuveyt turk"], file: "kuveyt-turk.png", color: "#007f68", imageWidth: 128, imageHeight: 128 },
  { names: ["albaraka türk", "albaraka turk", "albaraka"], file: "albaraka-turk.png", color: "#b84f0c", imageWidth: 48, imageHeight: 48 },
  { names: ["türkiye finans", "turkiye finans"], file: "turkiye-finans.png", color: "#087b75", imageWidth: 1329, imageHeight: 513 },
  { names: ["vakıf katılım", "vakif katilim"], file: "vakif-katilim.png", color: "#356b9d", imageWidth: 128, imageHeight: 128 },
  { names: ["ziraat katılım", "ziraat katilim"], file: "ziraat-katilim.png", color: "#b91820", imageWidth: 96, imageHeight: 96 },
  { names: ["emlak katılım", "emlak katilim"], file: "emlak-katilim.png", color: "#08733a", imageWidth: 48, imageHeight: 48 },
  { names: ["hayat finans"], file: "hayat-finans.ico", color: "#59358a", imageWidth: 32, imageHeight: 32 },
  { names: ["tom katılım", "tom katilim", "tom bank", "t.o.m."], file: "tom-katilim.png", color: "#5d27af", imageWidth: 16, imageHeight: 16 },
  { names: ["dünya katılım", "dunya katilim"], file: "dunya-katilim.png", color: "#356f9e", imageWidth: 16, imageHeight: 16 },
  { names: ["adil katılım", "adil katilim"], file: "adil-katilim.png", color: "#007d78", imageWidth: 16, imageHeight: 16 },
];

export function getBankBrand(bank: string) {
  const normalizedBank = bank.trim().toLocaleLowerCase("tr-TR");
  if (!normalizedBank) return undefined;
  return bankBrands.find(({ names }) =>
    names.some((name) => normalizedBank.includes(name))
  );
}

export function getBankBrandColor(bank: string) {
  return getBankBrand(bank)?.color ?? "#365f74";
}

export function getBankInitials(bank: string) {
  const words = bank.trim().split(/\s+/).filter(Boolean);
  const initials = words.slice(0, 2).map((word) => word[0]).join("");
  return (initials || "KB").toLocaleUpperCase("tr-TR");
}

export function getBankLogoDimensions(brand: BankBrand, requestedSize: number) {
  const availableSize = Math.max(12, Math.floor(Math.max(16, requestedSize) * 0.78));
  const scale = Math.min(
    1,
    availableSize / Math.max(brand.imageWidth, brand.imageHeight)
  );
  return {
    width: Math.max(1, Math.round(brand.imageWidth * scale)),
    height: Math.max(1, Math.round(brand.imageHeight * scale)),
  };
}
