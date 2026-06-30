import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: '/verify', pathMatch: 'full' },
  {
    path: 'login',
    loadComponent: () =>
      import('./features/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'verify',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/verify/verify.component').then((m) => m.VerifyComponent),
  },
  {
    path: 'batch',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/batch/batch.component').then((m) => m.BatchComponent),
  },
  { path: '**', redirectTo: '/verify' },
];
