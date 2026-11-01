import fs from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { parse } from "@babel/parser";
const root = path.resolve(process.argv[2] || "reference/aicoin");
const manifest = JSON.parse(await fs.readFile(path.join(root, "manifest.json"), "utf8"));
const recovery = JSON.parse(await fs.readFile(path.join(root, "recovery-report.json"), "utf8"));
const modules = JSON.parse(await fs.readFile(path.join(root, "module-index.json"), "utf8"));
assert.equal(recovery.archive_sha256, manifest.archive_sha256);
assert.equal(modules.archive_sha256, manifest.archive_sha256);
const digest = bytes => createHash("sha256").update(bytes).digest("hex");
for (const file of manifest.files) assert.equal(digest(await fs.readFile(path.join(root, "renderer", file.path))), file.sha256, `Raw bytes drift: ${file.path}`);
const scripts = manifest.files.filter(file => file.path.endsWith(".js"));
assert.equal(recovery.files.length, scripts.length);
assert.equal(new Set(recovery.files.map(file => file.path)).size, scripts.length);
assert.equal(modules.files.length, scripts.length);
for (const file of scripts) {
  const recovered = recovery.files.find(item => item.path === file.path);
  assert.equal(recovered.status, "recovered", `Unrecovered file: ${file.path}`);
  assert.equal(recovered.input_sha256, file.sha256);
  const source = await fs.readFile(path.join(root, "readable", file.path.replace(/\.js$/, ""), "deobfuscated.js"), "utf8");
  assert.equal(digest(source), recovered.output_sha256);
  parse(source, { sourceType: "unambiguous", plugins: ["jsx"] });
}
const byFile = new Map(recovery.files.map(file => [file.path, file]));
const moduleIds = new Set(modules.modules.map(module => Number(module.id)));
const unresolved = new Set();
for (const module of modules.modules) {
  const recovered = byFile.get(module.source);
  assert.equal(module.source_sha256, recovered.input_sha256);
  assert.equal(module.recovered_sha256, recovered.output_sha256);
  const source = await fs.readFile(path.join(root, "modules", module.path), "utf8");
  assert.equal(digest(source), module.sha256);
  parse(source, { sourceType: "module", plugins: ["jsx"] });
  module.dependencies.filter(id => !moduleIds.has(id)).forEach(id => unresolved.add(id));
}
const result = { scope: "Byte identity and syntax only; not runtime equivalence or complete feature migration.",
  raw_files_verified: manifest.files.length, readable_scripts_verified: scripts.length, factories_verified: modules.modules.length,
  files_without_matched_factory: modules.files.filter(file => !file.module_count).map(file => file.path),
  unresolved_static_dependency_ids: [...unresolved].sort((a, b) => a - b) };
await fs.writeFile(path.join(root, "verification.json"), JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result));
