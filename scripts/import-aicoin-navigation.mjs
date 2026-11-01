// Import pure route data from the recovered factory, without running it.
import fs from "node:fs/promises";
import path from "node:path";
import { parse } from "@babel/parser";
import { createHash } from "node:crypto";
const root = path.resolve(process.argv[2] || "reference/aicoin");
const index = JSON.parse(await fs.readFile(path.join(root, "module-index.json"), "utf8"));
const record = index.modules.find(item => item.source === "main.js" && item.id === "99719");
if (!record) throw new Error("Recovered navigation factory missing");
const text = await fs.readFile(path.join(root, "modules", record.path), "utf8");
if (createHash("sha256").update(text).digest("hex") !== record.sha256) throw new Error("Factory drift");
const ast = parse(text, { sourceType: "module" });
const factory = ast.program.body.find(node => node.type === "ExportDefaultDeclaration")?.declaration;
const locals = new Map();
function constant(node) {
  if (node.type === "StringLiteral") return node.value;
  if (node.type === "Identifier" && locals.has(node.name)) return locals.get(node.name);
  if (node.type === "MemberExpression") {
    const object = constant(node.object);
    const key = node.computed ? constant(node.property) : node.property.name;
    if (!Object.hasOwn(object, key)) throw new Error(`Unknown constant property ${key}`);
    return object[key];
  }
  if (node.type === "ObjectExpression") {
    const result = Object.create(null);
    for (const property of node.properties) {
      if (property.type === "SpreadElement") Object.assign(result, constant(property.argument));
      else {
        if (property.type !== "ObjectProperty") throw new Error("Non-data property rejected");
        const key = property.computed ? constant(property.key) : property.key.name || property.key.value;
        result[key] = constant(property.value);
      }
    }
    return result;
  }
  throw new Error(`Executable or unknown syntax rejected: ${node.type}`);
}
for (const node of factory.body.body) if (node.type === "VariableDeclaration") {
  for (const declaration of node.declarations) locals.set(declaration.id.name, constant(declaration.init));
}
const data = [...locals.values()].filter(value => typeof value === "object");
const primary = data.find(value => value.EXCHANGE && value.HOMEPAGE);
const paths = data.find(value => value.EXCHANGE && value.AI_SCRIPT_COPILOT);
const labels = data.find(value => value[primary.EXCHANGE] === "行情");
if (!primary || !paths || !labels || labels[paths.INFO] !== "要闻" || labels[paths.NEWS] !== "快讯") throw new Error("Navigation contract changed; review before import");
const output = `// Generated from AiCoin ${index.archive_sha256}, recovered main.js factory 99719.\n// Pure navigation data only; no upstream bootstrap, IPC, network or credentials.\n` +
  `export const AICOIN_PATHS = Object.freeze(${JSON.stringify(paths, null, 2)});\n` +
  `export const AICOIN_LABELS = Object.freeze(${JSON.stringify(labels, null, 2)});\n`;
await fs.writeFile(path.resolve("src/aicoin-navigation.generated.js"), output);
console.log(JSON.stringify({ paths: Object.keys(paths).length, labels: Object.keys(labels).length, factory_sha256: record.sha256 }));
