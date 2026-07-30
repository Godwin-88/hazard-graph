import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_API_URL is set in Vercel dashboard (e.g. https://hazardgraph-api.onrender.com)
// In dev, it defaults to localhost:8000
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
