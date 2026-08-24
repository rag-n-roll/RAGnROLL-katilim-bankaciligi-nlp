import Image from "next/image";
import type { CSSProperties } from "react";
import styles from "./BankLogo.module.css";
import {
  getBankBrand,
  getBankInitials,
  getBankLogoDimensions,
} from "./bankBrand";

type BankLogoProps = {
  bank: string;
  size?: number;
  className?: string;
  decorative?: boolean;
  accessibleLabel?: string;
};

export default function BankLogo({
  bank,
  size = 36,
  className = "",
  decorative = false,
  accessibleLabel,
}: BankLogoProps) {
  const safeSize = Math.max(16, Math.round(size));
  const match = getBankBrand(bank);
  const label = accessibleLabel ?? `${bank} logosu`;
  const dimensions = match ? getBankLogoDimensions(match, safeSize) : null;
  const style = {
    width: safeSize,
    height: safeSize,
    "--bank-color": match?.color ?? "#365f74",
  } as CSSProperties;

  if (!match || !dimensions) {
    return (
      <span
        aria-hidden={decorative || undefined}
        aria-label={decorative ? undefined : label}
        className={`${styles.fallback} ${className}`}
        role={decorative ? undefined : "img"}
        style={style}
      >
        {getBankInitials(bank)}
      </span>
    );
  }

  return (
    <span
      aria-hidden={decorative || undefined}
      className={`${styles.logo} ${className}`}
      style={style}
    >
      <Image
        src={`/bank-logos/${match.file}`}
        alt={decorative ? "" : label}
        width={dimensions.width}
        height={dimensions.height}
      />
    </span>
  );
}
