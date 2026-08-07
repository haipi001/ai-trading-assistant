import { cp, mkdir, writeFile } from "node:fs/promises";

await mkdir("dist/client", { recursive: true });
await cp("dist/index.html", "dist/client/index.html");
await cp("dist/assets", "dist/client/assets", { recursive: true });

await mkdir("dist/server", { recursive: true });
await writeFile(
  "dist/server/index.js",
  `export default {
  fetch(request, env) {
    if (!env?.ASSETS) {
      return new Response("Static asset binding unavailable", { status: 503 });
    }
    return env.ASSETS.fetch(request);
  },
};
`,
);
