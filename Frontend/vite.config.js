import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],

  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8020",
        changeOrigin: true,
      },

      "/auth": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },

      "/risk-agent": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/risk-agent/, ""),
      },
    },
  },

  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});