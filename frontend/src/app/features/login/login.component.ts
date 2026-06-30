import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  template: `
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg)">
      <div style="width:100%;max-width:380px;padding:1rem">
        <div class="card">
          <div style="text-align:center;margin-bottom:1.5rem">
            <h1 style="font-size:1.5rem;font-weight:700">TTB Label Verifier</h1>
            <p style="color:var(--text-muted);font-size:0.875rem;margin-top:0.25rem">
              Enter your access key to continue
            </p>
          </div>

          <div *ngIf="error" class="alert-error">{{ error }}</div>

          <form [formGroup]="form" (ngSubmit)="onSubmit()">
            <div class="form-group">
              <label for="access_key">Access Key</label>
              <input
                id="access_key"
                type="password"
                formControlName="access_key"
                placeholder="••••••••"
                autocomplete="current-password"
              />
              <span class="error-text" *ngIf="keyCtrl.invalid && keyCtrl.touched">
                Access key is required
              </span>
            </div>

            <button
              type="submit"
              class="btn btn-primary"
              style="width:100%"
              [disabled]="loading"
            >
              <span *ngIf="loading" class="spinner"></span>
              {{ loading ? 'Signing in…' : 'Sign In' }}
            </button>
          </form>
        </div>
      </div>
    </div>
  `,
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  form = this.fb.group({
    access_key: ['', Validators.required],
  });

  get keyCtrl() { return this.form.controls.access_key; }

  loading = false;
  error: string | null = null;

  onSubmit(): void {
    this.form.markAllAsTouched();
    if (this.form.invalid) return;

    this.loading = true;
    this.error = null;

    this.api.login(this.keyCtrl.value!).subscribe({
      next: () => {
        this.auth.setLoggedIn(true);
        this.router.navigate(['/verify']);
      },
      error: (err) => {
        this.loading = false;
        const status = err?.status;
        if (status === 401 || status === 403) {
          this.error = 'Invalid access key.';
        } else {
          this.error = 'Could not connect to the server. Please try again.';
        }
      },
    });
  }
}
