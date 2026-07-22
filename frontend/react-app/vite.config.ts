import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(() => {
  const apiTarget = process.env.VITE_RAG_API_TARGET
    || process.env.VITE_API_TARGET
    || 'http://127.0.0.1:8000'
  const wikiApiTarget = process.env.VITE_WIKI_API_TARGET || apiTarget

  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api/media': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/api/wiki': {
          target: wikiApiTarget,
          changeOrigin: true,
        },
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
        },
        '/health': { target: apiTarget, changeOrigin: true },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test-setup.ts'],
      exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    },
  }
})
