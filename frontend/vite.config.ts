import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Keep the large libraries in their own long-cached files.
        manualChunks: {
          charts: ["chart.js", "react-chartjs-2"],
          map: ["leaflet", "react-leaflet"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
