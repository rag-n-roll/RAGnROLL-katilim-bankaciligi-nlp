import Image from "next/image";
import type { CSSProperties } from "react";
import styles from "./BankLogo.module.css";
import { getBankBrand } from "./bankBrand";

type BankLogoProps = {
  bank: string;
  size?: number;
  className?: string;
};

export default function BankLogo({ bank, size = 36, className = "" }: BankLogoProps) {
  const match = getBankBrand(bank);

  if (!match) {
    return <span className={`${styles.fallback} ${className}`}>{bank.slice(0, 2).toUpperCase()}</span>;
  }

  return (
    <span
      className={`${styles.logo} ${className}`}
      style={{ width: size, height: size, "--bank-color": match.color } as CSSProperties}
    >
      <Image
        src={`/bank-logos/${match.file}`}
        alt={`${bank} logosu`}
        width={size}
        height={size}
      />
    </span>
  );
}
