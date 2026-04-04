import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), "");

  // Environment variable validation on startup
  if (!env.VITE_SUPABASE_URL) {
    throw new Error("Missing VITE_SUPABASE_URL in .env file");
  }
  if (!env.VITE_SUPABASE_ANON_KEY) {
    throw new Error("Missing VITE_SUPABASE_ANON_KEY in .env file");
  }

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    build: {
      // Chunk splitting by route for optimal caching
      rollupOptions: {
        output: {
          manualChunks: (id) => {
            if (id.includes("node_modules")) {
              if (
                id.includes("react-router-dom") ||
                id.includes("react-router")
              ) {
                return "vendor-router";
              }
              if (id.includes("@supabase")) {
                return "vendor-supabase";
              }
              return "vendor";
            }
          },
        },
      },
    },
  };
});
