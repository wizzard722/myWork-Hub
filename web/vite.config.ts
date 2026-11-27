import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In ontwikkeling gaat /api naar de gateway (docker compose up).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": process.env.HUB_GATEWAY ?? "http://localhost:8080" },
  },
});
