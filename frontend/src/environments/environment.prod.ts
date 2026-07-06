// Production environment — /api/* is routed to the FastAPI backend by nginx
// (see deploy/nginx.conf). No absolute URL needed; same-origin relative paths work.
//
// To override the API base at Docker build time, pass a build arg and use
// sed/envsubst in the Dockerfile to replace this value before `ng build`, e.g.:
//   docker build --build-arg API_BASE=/api .
export const environment = {
  production: true,
  apiBase: '/api',
};
