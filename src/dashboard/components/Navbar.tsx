"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import styles from "./Navbar.module.css";

const navItems = [
  { label: "Ana Sayfa", href: "/", icon: "home" },
  { label: "Karşılaştırma", href: "/compare", icon: "compare" },
  { label: "Kampanyalar", href: "/campaigns", icon: "campaign" },
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


  return (
    <svg className={styles.navIcon} viewBox="0 0 24 24" aria-hidden="true">
      <path d="m20 13-7 7-9-9V4h7l9 9Z" />
      <circle cx="8.3" cy="8.3" r="1.35" />
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
          <svg
            className={styles.brandMark}
            viewBox="0 0 48 48"
            aria-hidden="true"
            focusable="false"
          >
            <defs>
              <linearGradient id="compassGold" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#f3d579" />
                <stop offset="1" stopColor="#dca62e" />
              </linearGradient>
              <linearGradient id="compassTeal" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#d7ae52" />
                <stop offset="1" stopColor="#936b20" />
              </linearGradient>
            </defs>

            <circle className={styles.compassHalo} cx="24" cy="24" r="21" />
            <circle className={styles.compassRing} cx="24" cy="24" r="17" />
            <circle className={styles.compassOrbit} cx="24" cy="24" r="13.5" />

            <g className={styles.compassNeedle}>
              <path className={styles.compassWest} d="M7.5 24 21 19.5 18.5 24 21 28.5 7.5 24Z" />
              <path className={styles.compassEast} d="M40.5 24 27 19.5 29.5 24 27 28.5 40.5 24Z" />
              <path className={styles.compassNorth} d="M24 5.5 31 24 24 20 17 24 24 5.5Z" />
              <path className={styles.compassSouth} d="M24 42.5 17 24 24 28 31 24 24 42.5Z" />
              <path className={styles.compassShine} d="M24 8 24 20 19.3 22.7 24 8Z" />
              <circle className={styles.compassCenter} cx="24" cy="24" r="3.5" />
            </g>

            <circle className={styles.compassNode} cx="6.8" cy="24" r="1.65" />
            <circle className={styles.compassNode} cx="41.2" cy="24" r="1.65" />
            <circle className={styles.compassAccent} cx="24" cy="3.8" r="1.9" />
          </svg>

          <span className={styles.brandText}>
            <span>PUSULA</span>
            <strong>KATILIM</strong>
          </span>
        </Link>

        <span className={styles.navbarGlint} aria-hidden="true">
          <svg className={styles.glintCompass} viewBox="0 0 48 48">
            <circle className={styles.compassHalo} cx="24" cy="24" r="21" />
            <circle className={styles.compassRing} cx="24" cy="24" r="17" />
            <path className={styles.glintCompassReflection} d="M13 14 A16 16 0 0 1 35 16" />
            <circle className={styles.compassOrbit} cx="24" cy="24" r="13.5" />
            <g className={styles.compassNeedle}>
              <path className={styles.compassWest} d="M7.5 24 21 19.5 18.5 24 21 28.5 7.5 24Z" />
              <path className={styles.compassEast} d="M40.5 24 27 19.5 29.5 24 27 28.5 40.5 24Z" />
              <path className={styles.compassNorth} d="M24 5.5 31 24 24 20 17 24 24 5.5Z" />
              <path className={styles.compassSouth} d="M24 42.5 17 24 24 28 31 24 24 42.5Z" />
              <path className={styles.compassShine} d="M24 8 24 20 19.3 22.7 24 8Z" />
              <circle className={styles.compassCenter} cx="24" cy="24" r="3.5" />
            </g>
            <circle className={styles.compassNode} cx="6.8" cy="24" r="1.65" />
            <circle className={styles.compassNode} cx="41.2" cy="24" r="1.65" />
            <circle className={styles.compassAccent} cx="24" cy="3.8" r="1.9" />
          </svg>
        </span>

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
                  key={item.href}
                  href={item.href}
                  aria-label={item.label}
                  aria-current={isActive ? "page" : undefined}
                  className={`${styles.navLink} ${
                    isActive ? styles.active : ""
                  }`}
                  onClick={closeMenu}
                >
                  <NavIcon name={item.icon} />

                  <span className={styles.navLabel} aria-hidden="true">
                    {item.label}
                  </span>
                </Link>
              );
            })}
          </div>

          <Link
            href="/chatbot"
            aria-current={pathname === "/chatbot" ? "page" : undefined}
            className={`${styles.aiButton} ${
              pathname === "/chatbot" ? styles.aiActive : ""
            }`}
            onClick={closeMenu}
          >
            <span className={styles.aiIcon} aria-hidden="true">✦</span>
            AI Asistan
          </Link>
        </nav>
      </div>
    </header>
  );
}
