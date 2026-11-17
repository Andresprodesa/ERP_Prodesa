import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api -> backend FastAPI local (ver docs/API_CONTRATO.md).
// En producción el frontend se sirve como estático y /api apunta al backend por configuración.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
