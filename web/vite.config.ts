import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The live lane (POST /api/resolve, GET /api/resolve/stream) is served by the FastAPI backend
// (verdict/webapp.py) on :8010. Proxy /api to it so the dev UI is same-origin — no CORS, and SSE
// streams straight through. The frozen deck (/cards.json etc.) is still served statically by Vite.
const API = process.env.VERDICT_API || 'http://localhost:8010'

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.PORT) || 5175,
    strictPort: false,
    proxy: { '/api': { target: API, changeOrigin: true } },
  },
})
