import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies REST + WebSocket to the FastAPI backend (Phase 2),
// so the frontend talks to a single origin and avoids CORS / WS-origin issues.
// Change the target if your backend runs elsewhere.
const BACKEND = process.env.VITE_BACKEND ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/runs": { target: BACKEND, changeOrigin: true, ws: true },
      "/health": { target: BACKEND, changeOrigin: true },
    },
  },
});
