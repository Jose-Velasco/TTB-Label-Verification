import { provideHttpClient, withInterceptors } from "@angular/common/http";
import { ApplicationConfig } from "@angular/core";
import { provideRouter } from "@angular/router";
import { routes } from "./app.routes";
import { credentialsInterceptor } from "./core/interceptors/credentials.interceptor";

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    // provideHttpClient(withFetch(), withInterceptors([credentialsInterceptor])),
    provideHttpClient(withInterceptors([credentialsInterceptor])),
  ],
};
