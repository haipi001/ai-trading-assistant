import {fileURLToPath} from 'node:url';
import {defineConfig} from 'vite';
import {terminalThemePlugin} from './scripts/terminal-theme.mjs';
export default defineConfig({base:'./',resolve:{alias:process.env.TERMINAL_SOURCE_DIR?{'../../terminal-ui':fileURLToPath(new URL('./terminal-ui',import.meta.url))}:{}},css:{postcss:{plugins:[terminalThemePlugin()]}},build:{outDir:process.env.TERMINAL_FEATURE_OUTDIR||'../terminal-ui/features',emptyOutDir:true,rollupOptions:{input:['terminal-feature.html','local-data-migration.html']}}});
