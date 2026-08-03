import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Locally the SPA and the API share an origin: the dev server proxies `/api` to
// the backend, so the default `API_BASE = '/api'` needs no configuration. On
// Render the two are separate origins and VITE_API_BASE takes over at build time.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API_PROXY || 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
