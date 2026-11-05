import { resolve } from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds the browser extension separately, so the dashboard build is unaffected.
export default defineConfig({
  root: resolve(__dirname, 'extension'),
  base: './',
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, 'dist-extension'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        popup: resolve(__dirname, 'extension/popup.html'),
        background: resolve(__dirname, 'extension/src/background.js'),
        offscreen: resolve(__dirname, 'extension/offscreen.html'),
      },
      output: {
        entryFileNames: (chunk) => (chunk.name === 'background' ? 'background.js' : 'assets/[name]-[hash].js'),
      },
    },
  },
});
