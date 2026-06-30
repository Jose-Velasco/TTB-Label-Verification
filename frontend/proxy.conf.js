/**
 * Angular dev server proxy config — forwards /api/* to the FastAPI backend.
 * Uses process.env so the target is injectable from docker-compose without
 * baking a hostname into source code.
 *
 * Local dev (outside Docker): defaults to http://localhost:8000
 * Inside docker-compose.dev.yml: BACKEND_URL=http://backend:8000
 */
module.exports = {
  '/api': {
    target: process.env['BACKEND_URL'] || 'http://localhost:8000',
    secure: false,
    changeOrigin: true,
    logLevel: 'info',
  },
};
