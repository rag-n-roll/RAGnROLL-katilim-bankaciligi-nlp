import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(new URL("./Navbar.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("./Navbar.module.css", import.meta.url), "utf8");

test("navigasyon ana rotaları ve erişilebilir durumları korur", () => {
  assert.match(component, /label: "Ana Sayfa", href: "\/"/);
  assert.match(component, /label: "Karşılaştırma", href: "\/compare"/);
  assert.match(component, /label: "Kampanyalar", href: "\/campaigns"/);
  assert.doesNotMatch(component, /label: "Kalite", href: "\/quality"/);
  assert.match(component, /aria-current=/);
  assert.match(component, /aria-expanded=/);
  assert.match(component, /aria-controls="primary-navigation"/);
  assert.match(component, /aria-label="Ana navigasyon"/);
});

test("mobil menü, görünür focus ve reduced motion stilleri tanımlıdır", () => {
  assert.match(styles, /@media \(max-width: 760px\)/);
  assert.match(styles, /\.menuOpen\s*\{[^}]*display: grid/s);
  assert.match(styles, /:focus-visible/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
});
