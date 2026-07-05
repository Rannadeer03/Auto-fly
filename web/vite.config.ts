import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    // Production build is served by the FastAPI backend (server/static).
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // Split large, rarely-changing libraries into their own cacheable
        // chunks so a normal app-code deploy doesn't force re-downloading
        // MapLibre GL (the single biggest dependency) every time.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('maplibre-gl') || id.includes('terra-draw')) return 'vendor-maplibre'
          if (id.includes('react-dom') || id.includes('/react/')) return 'vendor-react'
          if (id.includes('@tanstack')) return 'vendor-query'
          if (id.includes('framer-motion')) return 'vendor-motion'
          return 'vendor'
        },
      },
    },
  },
  server: {
    port: 5173,
    host: true,
  },
})
