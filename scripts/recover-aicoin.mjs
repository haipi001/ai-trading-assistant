// Recover readable copies; never import or execute the application bundle.
// webcrack runs string decoders in isolated-vm, not the app bootstrap.
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";

const root = path.resolve(process.argv[2] || "reference/aicoin");
const cli = process.env.AICOIN_WEBCRACK_CLI;
if (!cli || !path.isAbsolute(cli)) throw new Error("Set AICOIN_WEBCRACK_CLI to an installed webcrack 2.16.0 CLI file");
const manifest = JSON.parse(await fs.readFile(path.join(root, "manifest.json"), "utf8"));
const output = path.join(root, "readable");
await fs.mkdir(output, { recursive: true });
const reportPath = path.join(root, "recovery-report.json");
let report;
try { report = JSON.parse(await fs.readFile(reportPath, "utf8")); }
catch (error) { if (error.code !== "ENOENT") throw error; }
report ||= { tool: "webcrack", version: "2.16.0", archive_sha256: manifest.archive_sha256, files: [] };
if (report.archive_sha256 !== manifest.archive_sha256) throw new Error("Archive identity changed");
const digest = bytes => createHash("sha256").update(bytes).digest("hex");
const files = manifest.files.filter(file => file.path.endsWith(".js"));
// Process entry first, then small application chunks before large libraries.
files.sort((a, b) => (a.path === "main.js" ? -1 : b.path === "main.js" ? 1 : a.size - b.size));
for (const file of files) {
  const input = path.join(root, "renderer", file.path);
  const dir = path.join(output, file.path.replace(/\.js$/, ""));
  const generated = path.join(dir, "deobfuscated.js");
  const bytes = await fs.readFile(input);
  if (digest(bytes) !== file.sha256) throw new Error(`Input drift: ${file.path}`);
  const previous = report.files.find(item => item.path === file.path);
  if (previous?.status === "recovered" && digest(await fs.readFile(generated)) === previous.output_sha256) continue;
  if (previous) continue; // Failed attempts require explicit review, not automatic replay.
  const disk = await fs.statfs(root);
  if (disk.bavail * disk.bsize < 1024 ** 3) throw new Error("Less than 1 GiB free; recovery paused before creating more files");
  try { await fs.access(dir); throw new Error(`Unreviewed existing output: ${dir}`); }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  const log = await fs.open(path.join(output, file.path + ".log"), "wx");
  const started = Date.now();
  const child = spawn(process.execPath, ["--max-old-space-size=2048", cli, input, "-o", dir], { stdio: ["ignore", log.fd, log.fd] });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; child.kill("SIGTERM"); }, 180000);
  let exitCode = null;
  let failure = null;
  try { exitCode = await new Promise((resolve, reject) => { child.once("error", reject); child.once("exit", resolve); }); }
  catch (error) { failure = error.message; }
  finally { clearTimeout(timer); await log.close(); }
  let result;
  try { result = await fs.readFile(generated); } catch {}
  const entry = { path: file.path, input_sha256: file.sha256, exit_code: exitCode, timed_out: timedOut,
    status: exitCode === 0 && result ? "recovered" : "failed", elapsed_ms: Date.now() - started,
    ...(failure ? { error: failure } : {}), ...(result ? { output_sha256: digest(result), output_bytes: result.length } : {}) };
  report.files.push(entry);
  await fs.writeFile(reportPath + ".tmp", JSON.stringify(report, null, 2) + "\n");
  await fs.rename(reportPath + ".tmp", reportPath);
  console.log(JSON.stringify({ ...entry, done: report.files.length, total: files.length }));
}
