import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // Forwards API calls to the FastAPI app when mocks are turned off.
    proxy: { '/api': 'http://localhost:8000' },
  },
});
