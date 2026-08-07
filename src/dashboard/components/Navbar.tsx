"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./Navbar.module.css";

const navItems = [
  { label: "Ana Sayfa", href: "/" },
  { label: "Karşılaştırma", href: "/compare" },
  { label: "Kampanyalar", href: "/campaigns" },
];

export default function Navbar() {
  const pathname = usePathname();

  return (
    <header className={styles.navbar}>
      <div className={styles.container}>
        <Link href="/" className={styles.brand}>
          Katılım Bankacılığı
        </Link>

        <nav className={styles.navigation}>
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`${styles.navLink} ${
                pathname === item.href ? styles.active : ""
              }`}
            >
              {item.label}
            </Link>
          ))}

          <Link
            href="/chatbot"
            className={`${styles.aiButton} ${
              pathname === "/chatbot" ? styles.aiActive : ""
            }`}
          >
            <span className={styles.aiIcon}>✦</span>
            AI Asistan
          </Link>
        </nav>
      </div>
    </header>
  );
}