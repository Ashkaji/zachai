import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": {
        // On utilise BACKEND_URL pour le proxy interne
        // Si non défini, on tente localhost:8000 (dev hors docker)
        target: process.env.BACKEND_URL || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          // Keep React together to avoid runtime ordering issues.
          if (id.includes("react-dom") || id.includes("/react/") || id.includes("scheduler")) {
            return "react-vendor";
          }
          if (id.includes("@tiptap") || id.includes("prosemirror")) {
            return "tiptap-vendor";
          }
          if (id.includes("yjs") || id.includes("lib0") || id.includes("@hocuspocus")) {
            return "collab-vendor";
          }
          if (id.includes("oidc") || id.includes("react-oidc-context")) {
            return "oidc-vendor";
          }
        },
      },
    },
  },
});
