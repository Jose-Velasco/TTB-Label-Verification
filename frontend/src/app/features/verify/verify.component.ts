import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive, Router } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { ApplicationData, VerificationResult } from '../../models/label.models';
import { ApplicationFormComponent } from '../../shared/components/application-form/application-form.component';
import { LabelUploaderComponent } from '../../shared/components/label-uploader/label-uploader.component';
import { CameraCaptureComponent } from '../../shared/components/camera-capture/camera-capture.component';
import { VerificationResultComponent } from '../../shared/components/verification-result/verification-result.component';

@Component({
  selector: 'app-verify',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    RouterLinkActive,
    ApplicationFormComponent,
    LabelUploaderComponent,
    CameraCaptureComponent,
    VerificationResultComponent,
  ],
  template: `
    <div class="container">
      <nav class="nav">
        <a routerLink="/verify" routerLinkActive="active">Single Verify</a>
        <a routerLink="/batch" routerLinkActive="active">Batch</a>
        <button class="btn btn-secondary" style="margin-left:auto;padding:0.375rem 0.875rem;font-size:0.8125rem" (click)="logout()">
          Sign Out
        </button>
      </nav>

      <div class="page-header">
        <div>
          <h1>Label Verification</h1>
          <p>Upload a label image and enter application data to verify compliance.</p>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem">
        <div>
          <app-application-form (saved)="onAppDataSaved($event)" />

          <div *ngIf="appData" class="card" style="background:var(--bg);margin-top:0">
            <p style="font-size:0.8125rem;color:var(--pass);font-weight:600">✓ Application data saved</p>
          </div>
        </div>

        <div>
          <div class="card">
            <h2 style="font-size:1.125rem;font-weight:700;margin-bottom:1rem">Label Image</h2>

            <div style="display:flex;gap:0.75rem;margin-bottom:1rem">
              <button
                class="btn"
                [class.btn-primary]="inputMode === 'upload'"
                [class.btn-secondary]="inputMode !== 'upload'"
                (click)="inputMode = 'upload'"
              >Upload</button>
              <button
                class="btn"
                [class.btn-primary]="inputMode === 'camera'"
                [class.btn-secondary]="inputMode !== 'camera'"
                (click)="inputMode = 'camera'"
              >Camera</button>
            </div>

            <app-label-uploader
              *ngIf="inputMode === 'upload'"
              (fileSelected)="onFileSelected($event)"
            />
            <app-camera-capture
              *ngIf="inputMode === 'camera'"
              (fileSelected)="onFileSelected($event)"
            />
          </div>

          <div style="margin-top:1rem">
            <div *ngIf="error" class="alert-error">{{ error }}</div>

            <button
              class="btn btn-primary"
              style="width:100%"
              [disabled]="loading || !selectedFile || !appData"
              (click)="verify()"
            >
              <span *ngIf="loading" class="spinner"></span>
              {{ loading ? 'Verifying…' : 'Verify Label' }}
            </button>

            <p *ngIf="!appData || !selectedFile" style="font-size:0.8125rem;color:var(--text-muted);margin-top:0.5rem;text-align:center">
              {{ !appData ? 'Save application data first.' : 'Select a label image.' }}
            </p>
          </div>
        </div>
      </div>

      <div *ngIf="result" style="margin-top:1.5rem">
        <app-verification-result [result]="result" />
      </div>
    </div>
  `,
})
export class VerifyComponent {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  inputMode: 'upload' | 'camera' = 'upload';
  appData: ApplicationData | null = null;
  selectedFile: File | null = null;
  loading = false;
  error: string | null = null;
  result: VerificationResult | null = null;

  onAppDataSaved(data: ApplicationData): void {
    this.appData = data;
  }

  onFileSelected(file: File): void {
    this.selectedFile = file;
    this.result = null;
    this.error = null;
  }

  verify(): void {
    if (!this.selectedFile || !this.appData) return;

    this.loading = true;
    this.error = null;
    this.result = null;

    this.api.verify(this.selectedFile, this.appData).subscribe({
      next: (r) => {
        this.result = r;
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        if (err?.status === 401 || err?.status === 403) {
          this.auth.setLoggedIn(false);
          this.router.navigate(['/login']);
        } else if (err?.status === 429) {
          this.error = 'Rate limit reached. Please wait a moment and try again.';
        } else {
          this.error = err?.error?.detail ?? 'Verification failed. Please try again.';
        }
      },
    });
  }

  logout(): void {
    this.api.logout().subscribe({
      complete: () => {
        this.auth.setLoggedIn(false);
        this.router.navigate(['/login']);
      },
      error: () => {
        this.auth.setLoggedIn(false);
        this.router.navigate(['/login']);
      },
    });
  }
}
