import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/ui/',
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:5156',
      '/tasks': 'http://localhost:5156',
      '/workflows': 'http://localhost:5156',
      '/dashboard': 'http://localhost:5156',
      '/agents': 'http://localhost:5156',
      '/health': 'http://localhost:5156',
    },
  },
})
