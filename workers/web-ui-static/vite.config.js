import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "assets",
    emptyOutDir: false,
    cssCodeSplit: false,
    lib: {
      entry: "ui/chrome.js",
      name: "StockRadarChromeBundle",
      formats: ["iife"],
      fileName: () => "chrome.js",
    },
    rollupOptions: {
      output: {
        assetFileNames: "chrome.css",
        inlineDynamicImports: true,
      },
    },
  },
});
