// Development environment — API calls go to /api/* which the Angular dev server
// proxies to the FastAPI backend (see proxy.conf.js).
export const environment = {
  production: false,
  apiBase: '/api',
};
