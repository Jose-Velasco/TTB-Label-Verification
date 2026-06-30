import { HttpInterceptorFn } from '@angular/common/http';

// Attaches withCredentials: true to every outgoing request so the browser
// sends the httpOnly auth cookie set by FastAPI's /api/login endpoint.
// In Angular, a functional interceptor replaces the old class-based HttpInterceptor.
export const credentialsInterceptor: HttpInterceptorFn = (req, next) =>
  next(req.clone({ withCredentials: true }));
