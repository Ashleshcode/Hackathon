// If API_URL changes host or port, update host_permissions in manifest.json too.
export const API_URL = 'http://localhost:8000';
// Demo results link to fixtures in the dashboard's mock mode, and Live results to
// campaigns on the real backend, so each mode has its own dashboard address.
export const DASHBOARD_URLS = { demo: 'http://localhost:5173', live: 'http://localhost:5174' };
export const ANALYZE_TIMEOUT_MS = 60000;
