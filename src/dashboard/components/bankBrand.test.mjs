import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  bankBrands,
  getBankBrand,
  getBankInitials,
  getBankLogoDimensions,
} from "./bankBrand.ts";

test("on banka markası ve asset metadatası eşleşir", () => {
  assert.equal(bankBrands.length, 10);
  for (const brand of bankBrands) {
    const asset = new URL(`../public/bank-logos/${brand.file}`, import.meta.url);
    const bytes = readFileSync(asset);
    assert.ok(bytes.length > 0, `${brand.file} boş olmamalı`);
    if (brand.file.endsWith(".png")) {
      assert.equal(bytes.readUInt32BE(16), brand.imageWidth, `${brand.file} genişliği`);
      assert.equal(bytes.readUInt32BE(20), brand.imageHeight, `${brand.file} yüksekliği`);
    }
  }
});

test("Türkçe ve ASCII banka adları aynı markayı bulur", () => {
  assert.equal(getBankBrand("Kuveyt Türk")?.file, "kuveyt-turk.png");
  assert.equal(getBankBrand("Vakif Katilim Bankasi")?.file, "vakif-katilim.png");
  assert.equal(getBankBrand("T.O.M. Bank")?.file, "tom-katilim.png");
  assert.equal(getBankBrand("Bilinmeyen Banka"), undefined);
});

test("fallback baş harfleri ve düşük çözünürlük güvenlidir", () => {
  assert.equal(getBankInitials("Örnek Katılım"), "ÖK");
  assert.equal(getBankInitials(""), "KB");
  const lowResolution = getBankBrand("Adil Katılım");
  assert.ok(lowResolution);
  assert.deepEqual(getBankLogoDimensions(lowResolution, 64), { width: 16, height: 16 });
  assert.deepEqual(getBankLogoDimensions(lowResolution, 16), { width: 12, height: 12 });
});
