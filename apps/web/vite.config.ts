import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/providers": "http://127.0.0.1:8000",
      "/jobs": "http://127.0.0.1:8000",
      "/outputs": "http://127.0.0.1:8000",
      "/files": "http://127.0.0.1:8000",
    },
  },
});
