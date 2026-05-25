import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, "../static"),
    emptyOutDir: false,
    rollupOptions: {
      output: {
        entryFileNames: "js/dashboard.js",
        chunkFileNames: "js/[name].js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".css")) {
            return "css/dashboard.css";
          }
          return "assets/[name][extname]";
        },
      },
    },
  },
});

