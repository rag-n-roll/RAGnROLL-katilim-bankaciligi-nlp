export type FormattedBlock =
  | { type: "heading"; text: string }
  | { type: "list"; items: string[]; ordered: boolean }
  | { type: "paragraph"; text: string };

const BULLET_REGEX = /^([•\-\*⁃‣▪▫–—]|\d+[\.\)]|[a-zA-Z][\.\)])\s+/;
const NUMBERED_REGEX = /^\d+[\.\)]\s+/;

const STANDALONE_HEADERS: Record<string, true> = {
  "kampanya koşulları": true,
  "kampanya detayları": true,
  "kampanya şartları": true,
  "kampanya dönemi": true,
  "kampanya kuralları": true,
  "kampanya tarihleri": true,
  "kampanya hakkında": true,
  "kampanyaya katılım": true,
  "kampanyaya nasıl katılırım": true,
  "kampanyadan kimler faydalanabilir": true,
  "kampanyadan nasıl yararlanırım": true,
  "genel şartlar": true,
  "katılım koşulları": true,
  "katılım şartları": true,
  "önemli bilgiler": true,
  "dikkat edilmesi gerekenler": true,
  "nasıl kazanırım": true,
  "ödül ve kullanım": true,
  "kampanya başlangıç ve bitiş tarihi": true,
  "kampanya başlangıç ve bitiş tarihleri": true,
  "kampanya süresi": true,
  "ek kampanya detayları": true,
  "parafpara yüklenmesi ne zaman yapılır": true,
  sektör: true,
  ürün: true,
  hediye: true,
  ödül: true,
  kazanç: true,
};

/**
 * Checks whether a single line represents a standalone section title,
 * question-based heading, or key-value metadata label.
 */
export function isHeadingLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed || trimmed.length > 120) return false;

  // Lines ending with conjunctions or opening quotes are incomplete sentences, not headers
  if (
    /([“"‘'–—\-]|\b(ve|veya|ile|için|olan|gibi|kadar|göre|üzere|olarak)\b)$/i.test(
      trimmed
    )
  ) {
    return false;
  }

  // Key-value metadata pattern like "Sektör: Araba Kiralama" or "Son Katılım: 31.12.2026"
  const labelMatch = trimmed.match(/^([A-Za-zÇĞİÖŞÜçğıöşü\s]{2,30}):\s*(.*)$/);
  if (labelMatch) {
    const labelKey = labelMatch[1].trim().toLocaleLowerCase("tr-TR");
    const rest = labelMatch[2].trim();
    if (
      STANDALONE_HEADERS[labelKey] ||
      rest.length === 0 ||
      rest.split(/\s+/).length <= 6
    ) {
      return true;
    }
  }

  // Question or colon ending with a reasonable word count
  if (
    (trimmed.endsWith(":") || trimmed.endsWith("?")) &&
    trimmed.split(/\s+/).length <= 14
  ) {
    return true;
  }

  const clean = trimmed
    .replace(/[:\?]+$/, "")
    .trim()
    .toLocaleLowerCase("tr-TR");
  return Boolean(STANDALONE_HEADERS[clean]);
}

/**
 * Cleans punctuation spacing, apostrophe attachments, and numeric formatting.
 */
export function cleanTextPunctuation(text: string): string {
  return text
    .replace(/\s+/g, " ")
    .replace(/\s+([,\.\!\?\:\;])/g, "$1")
    .replace(/([\(“‘])\s+/g, "$1")
    .replace(/\s+([\)\”’])/g, "$1")
    .replace(/(\d+)\s+([\.\,])\s+(\d+)/g, "$1$2$3")
    .replace(/(\d+)\s+TL\s*[\'’]\s*([a-zA-ZçğıöşüÇĞİÖŞÜ]+)/g, "$1 TL’$2")
    .replace(/(\d+)\s*%\s*/g, "%$1 ")
    .replace(/%\s+(\d+)/g, "%$1")
    .trim();
}

/**
 * Parses raw campaign text (containing broken scraping newlines, headings, and lists)
 * into semantic blocks (headings, lists, paragraphs).
 */
export function parseCampaignText(rawText?: string | null): FormattedBlock[] {
  if (!rawText || !rawText.trim()) return [];

  // Normalize newlines, zero-width chars, tabs, and non-breaking spaces
  const normalized = rawText
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/[\u00A0\u200B\u200C\u200D\uFEFF\t]/g, " ");

  const rawParagraphs = normalized.split(/\n\s*\n+/);
  const rawUnits: Array<{
    type: "heading" | "list_item" | "paragraph";
    content: string;
    ordered?: boolean;
  }> = [];

  for (const p of rawParagraphs) {
    const lines = p
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);

    if (lines.length === 0) continue;

    let curr = "";
    let currType: "list_item" | "paragraph" = "paragraph";
    let currOrdered = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (isHeadingLine(line)) {
        if (curr) {
          rawUnits.push({ type: currType, content: curr, ordered: currOrdered });
          curr = "";
        }
        rawUnits.push({ type: "heading", content: line });
        continue;
      }

      if (BULLET_REGEX.test(line)) {
        if (curr) {
          rawUnits.push({ type: currType, content: curr, ordered: currOrdered });
          curr = "";
        }
        currType = "list_item";
        currOrdered = NUMBERED_REGEX.test(line);
        curr = line.replace(BULLET_REGEX, "").trim();
        continue;
      }

      if (!curr) {
        curr = line;
        currType = "paragraph";
        currOrdered = false;
        continue;
      }

      // Check if current text ends with genuine terminal punctuation
      const isAbbrev =
        /(vb|vs|örn|dr|prof|no|apt|sok|cad|mah|sk|tl)\.\s*$/i.test(curr);
      const isNumberedDate = /\d{1,2}\.\s*$/.test(curr);
      const currEndsWithTerminal =
        /[\.\!\?]\s*$/.test(curr) && !isAbbrev && !isNumberedDate;

      const startsWithSuffix =
        /^([\'\’][a-zA-ZçğıöşüÇĞİÖŞÜ]+|[,\.\!\?\:\;\)\]\”’%])/.test(line);
      const startsWithLower = /^[a-zçğıöşü]/.test(line);

      // Check if previous line ended with hyphen or separator (e.g. date ranges)
      const isHyphenMerge =
        curr.endsWith("-") ||
        curr.endsWith("–") ||
        line === "-" ||
        line === "–";

      if (
        !currEndsWithTerminal ||
        startsWithSuffix ||
        startsWithLower ||
        isHyphenMerge
      ) {
        if (startsWithSuffix && /^[\'\’]/.test(line)) {
          curr += line;
        } else if (
          line.startsWith(",") ||
          line.startsWith(".") ||
          line.startsWith(";")
        ) {
          curr += line;
        } else {
          curr += " " + line;
        }
      } else {
        rawUnits.push({ type: currType, content: curr, ordered: currOrdered });
        curr = line;
        currType = "paragraph";
        currOrdered = false;
      }
    }

    if (curr) {
      rawUnits.push({ type: currType, content: curr, ordered: currOrdered });
    }
  }

  // Combine consecutive list items into list blocks
  const blocks: FormattedBlock[] = [];
  let pendingList: { items: string[]; ordered: boolean } | null = null;

  for (const unit of rawUnits) {
    const cleaned = cleanTextPunctuation(unit.content);
    if (!cleaned) continue;

    if (unit.type === "list_item") {
      const isOrdered = Boolean(unit.ordered);
      if (pendingList && pendingList.ordered === isOrdered) {
        pendingList.items.push(cleaned);
      } else {
        if (pendingList) {
          blocks.push({
            type: "list",
            items: pendingList.items,
            ordered: pendingList.ordered,
          });
        }
        pendingList = { items: [cleaned], ordered: isOrdered };
      }
    } else {
      if (pendingList) {
        blocks.push({
          type: "list",
          items: pendingList.items,
          ordered: pendingList.ordered,
        });
        pendingList = null;
      }

      if (unit.type === "heading") {
        blocks.push({ type: "heading", text: cleaned });
      } else {
        blocks.push({ type: "paragraph", text: cleaned });
      }
    }
  }

  if (pendingList) {
    blocks.push({
      type: "list",
      items: pendingList.items,
      ordered: pendingList.ordered,
    });
  }

  return blocks;
}

/**
 * Returns a cleaned plain-text string representation of the campaign content
 * with unified paragraphs and proper formatting.
 */
export function cleanCampaignText(rawText?: string | null): string {
  const blocks = parseCampaignText(rawText);
  if (blocks.length === 0) return "";

  return blocks
    .map((b) => {
      if (b.type === "heading") return b.text;
      if (b.type === "list") {
        return b.items
          .map((item, i) => `${b.ordered ? `${i + 1}.` : "•"} ${item}`)
          .join("\n");
      }
      return b.text;
    })
    .join("\n\n");
}
