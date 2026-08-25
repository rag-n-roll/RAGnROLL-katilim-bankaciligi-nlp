"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import styles from "./Navbar.module.css";

const navItems = [
  { label: "Ana Sayfa", href: "/", icon: "home" },
  { label: "Karşılaştırma", href: "/compare", icon: "compare" },
  { label: "Kampanyalar", href: "/campaigns", icon: "campaign" },
  { label: "Kalite", href: "/quality", icon: "quality" },
] as const;

function NavIcon({ name }: { name: (typeof navItems)[number]["icon"] }) {
  if (name === "home") {
    return (
      <svg className={styles.navIcon} viewBox="0 0 24 24" aria-hidden="true">
        <path d="m3.5 11.5 8.5-7 8.5 7" />
        <path d="M5.5 10v10h13V10M9.5 20v-6h5v6" />
      </svg>
    );
  }
  if (name === "compare") {
    return (
      <svg className={styles.navIcon} viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 7h13M14 4l3 3-3 3" />
        <path d="M20 17H7M10 14l-3 3 3 3" />
      </svg>
    );
  }
  if (name === "quality") {
    return (
      <svg className={styles.navIcon} viewBox="0 0 24 24" aria-hidden="true">
        <path d="m12 3 7 3v5c0 4.5-2.8 8-7 10-4.2-2-7-5.5-7-10V6l7-3Z" />
        <path d="m8.5 12 2.2 2.2 4.8-5" />
      </svg>
    );
  }
  return (
    <svg className={styles.navIcon} viewBox="0 0 24 24" aria-hidden="true">
      <path d="m20 13-7 7-9-9V4h7l9 9Z" />
      <circle cx="8.3" cy="8.3" r="1.35" />
    </svg>
  );
}

function BrandMark() {
  return (
    <svg className={styles.brandMark} viewBox="0 0 48 48" aria-hidden="true">
      <circle className={styles.compassHalo} cx="24" cy="24" r="21" />
      <circle className={styles.compassRing} cx="24" cy="24" r="17" />
      <circle className={styles.compassOrbit} cx="24" cy="24" r="13.5" />
      <g className={styles.compassNeedle}>
        <path className={styles.compassSide} d="M7.5 24 21 19.5 18.5 24 21 28.5 7.5 24Z" />
        <path className={styles.compassSide} d="M40.5 24 27 19.5 29.5 24 27 28.5 40.5 24Z" />
        <path className={styles.compassNorth} d="M24 5.5 31 24 24 20 17 24 24 5.5Z" />
        <path className={styles.compassSouth} d="M24 42.5 17 24 24 28 31 24 24 42.5Z" />
        <circle className={styles.compassCenter} cx="24" cy="24" r="3.5" />
      </g>
    </svg>
  );
}

export default function Navbar() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  return (
    <header
      className={styles.navbar}
      onKeyDown={(event) => {
        if (event.key === "Escape") setMenuOpen(false);
      }}
    >
      <div className={styles.container}>
        <Link href="/" className={styles.brand} onClick={closeMenu}>
          <BrandMark />
          <span className={styles.brandText}>
            <strong>Pusula</strong>
            <span>Katılım</span>
          </span>
        </Link>

        <button
          aria-controls="primary-navigation"
          aria-expanded={menuOpen}
          aria-label={menuOpen ? "Menüyü kapat" : "Menüyü aç"}
          className={styles.menuButton}
          onClick={() => setMenuOpen((open) => !open)}
          type="button"
        >
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <span aria-hidden="true" />
        </button>

        <nav
          aria-label="Ana navigasyon"
          className={`${styles.navigation} ${menuOpen ? styles.menuOpen : ""}`}
          id="primary-navigation"
        >
          <div className={styles.navGroup}>
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  aria-current={isActive ? "page" : undefined}
                  aria-label={item.label}
                  className={`${styles.navLink} ${isActive ? styles.active : ""}`}
                  href={item.href}
                  key={item.href}
                  onClick={closeMenu}
                >
                  <NavIcon name={item.icon} />
                  <span className={styles.navLabel}>{item.label}</span>
                </Link>
              );
            })}
          </div>
          <Link
            aria-current={pathname === "/chatbot" ? "page" : undefined}
            className={`${styles.aiButton} ${
              pathname === "/chatbot" ? styles.aiActive : ""
            }`}
            href="/chatbot"
            onClick={closeMenu}
          >
            <span aria-hidden="true" className={styles.aiIcon}>✦</span>
            AI Asistan
          </Link>
        </nav>
      </div>
    </header>
  );
}
