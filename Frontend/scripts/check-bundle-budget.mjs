import fs from "node:fs";
import path from "node:path";

const distAssets = path.join(process.cwd(), "dist", "assets");
if (!fs.existsSync(distAssets)) {
  console.error("dist/assets does not exist. Run build first.");
  process.exit(1);
}

const maxJsKb = Number.parseInt(process.env.VITE_MAX_JS_BUNDLE_KB || "550", 10);
const files = fs.readdirSync(distAssets).filter((file) => file.endsWith(".js"));

if (files.length === 0) {
  console.error("No JS bundles found in dist/assets");
  process.exit(1);
}

let total = 0;
for (const file of files) {
  const sizeKb = fs.statSync(path.join(distAssets, file)).size / 1024;
  total += sizeKb;
}

console.log(`Bundle total: ${total.toFixed(2)} KB (limit ${maxJsKb} KB)`);
if (total > maxJsKb) {
  console.error(`Bundle budget exceeded by ${(total - maxJsKb).toFixed(2)} KB`);
  process.exit(1);
}
