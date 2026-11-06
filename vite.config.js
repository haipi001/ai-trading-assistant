import { defineConfig } from "vite";

export default defineConfig({
  build:{rollupOptions:{input:["index.html","local-data-migration.html"]}},
  base: process.env.GITHUB_ACTIONS ? "/ai-trading-assistant/" : "/",
});
