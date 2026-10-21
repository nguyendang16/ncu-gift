import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The FastAPI backend runs on :8000 by default; /api is proxied so the browser never needs CORS in development.
// PORT and NCU_API_PORT let a second copy run beside the first (e.g. while verifying a change).
const api = `http://127.0.0.1:${process.env.NCU_API_PORT ?? 8000}`;
export default defineConfig({
  plugins: [react()],
  server: { port: Number(process.env.PORT ?? 5173), proxy: { "/api": api },allowedHosts: [
      'c74f-140-115-126-63.ngrok-free.app',
    ], },
});
