import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { parse } from "@babel/parser";

const root = path.resolve(process.argv[2] || "reference/aicoin");
const manifest = JSON.parse(await fs.readFile(path.join(root, "manifest.json"), "utf8"));
const index = { version: manifest.app_version, archive_sha256: manifest.archive_sha256,
  scope: "Static literal candidates only. No dynamic route resolution or runtime reachability claim.", files: [], routes: [] };
const routes = new Map();
function visit(node, file) {
  if (!node || typeof node !== "object") return;
  if (node.type === "StringLiteral" && /^\/(?:main|chart|account|settings|community|login|auth|order|script|flash|float|chat|screener|hl-)[\w/{}:?.=-]*$/.test(node.value)) {
    const entry = routes.get(node.value) || { path: node.value, occurrences: [] };
    entry.occurrences.push({ file, start: node.start, end: node.end });
    routes.set(node.value, entry);
  }
  for (const [key, value] of Object.entries(node)) {
    if (["loc", "extra", "comments", "tokens"].includes(key)) continue;
    if (Array.isArray(value)) value.forEach(child => visit(child, file));
    else if (value && typeof value === "object") visit(value, file);
  }
}
for (const file of manifest.files.filter(file => file.path.endsWith(".js"))) {
  const source = await fs.readFile(path.join(root, "renderer", file.path), "utf8");
  const sha256 = createHash("sha256").update(source).digest("hex");
  if (sha256 !== file.sha256) throw new Error(`Imported source drift: ${file.path}`);
  try {
    const ast = parse(source, { sourceType: "unambiguous" });
    visit(ast, file.path);
    index.files.push({ path: file.path, sha256, parsed: true });
  } catch (error) {
    index.files.push({ path: file.path, sha256, parsed: false, error: error.message });
  }
}
index.routes = [...routes.values()].sort((a, b) => a.path.localeCompare(b.path));
index.parsed_count = index.files.filter(file => file.parsed).length;
await fs.writeFile(path.join(root, "literal-index.json"), JSON.stringify(index, null, 2) + "\n");
console.log(JSON.stringify({ files: index.files.length, parsed: index.parsed_count, literal_route_candidates: index.routes.length }));
