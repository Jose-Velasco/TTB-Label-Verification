import { CommonModule } from "@angular/common";
import { Component, inject, signal } from "@angular/core";
import { Router, RouterLink, RouterLinkActive } from "@angular/router";
import { ApiService } from "../../core/services/api.service";
import { AuthService } from "../../core/services/auth.service";
import {
  ApplicationData,
  ExtractedApplicationData,
  VerificationResult,
} from "../../models/label.models";
import { ApplicationFormComponent } from "../../shared/components/application-form/application-form.component";
import { CameraCaptureComponent } from "../../shared/components/camera-capture/camera-capture.component";
import { LabelUploaderComponent } from "../../shared/components/label-uploader/label-uploader.component";
import { VerificationResultComponent } from "../../shared/components/verification-result/verification-result.component";

@Component({
  selector: "app-verify",
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
        <button
          class="btn btn-secondary"
          style="margin-left:auto;padding:0.375rem 0.875rem;font-size:0.8125rem"
          (click)="logout()"
        >
          Sign Out
        </button>
      </nav>

      <div class="page-header">
        <div>
          <h1>Label Verification</h1>
          <p>
            Upload a label image and enter application data to verify
            compliance.
          </p>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem">
        <div>
          <app-application-form
            (saved)="onAppDataSaved($event)"
            [autoFill]="extractedData()"
          />

          <div
            *ngIf="appData()"
            class="card"
            style="background:var(--bg);margin-top:0"
          >
            <p style="font-size:0.8125rem;color:var(--pass);font-weight:600">
              ✓ Application data saved
            </p>
          </div>
        </div>

        <div>
          <div class="card">
            <h2 style="font-size:1.125rem;font-weight:700;margin-bottom:1rem">
              Label Image
            </h2>

            <div style="display:flex;gap:0.75rem;margin-bottom:1rem">
              <button
                class="btn"
                [class.btn-primary]="inputMode() === 'upload'"
                [class.btn-secondary]="inputMode() !== 'upload'"
                (click)="inputMode.set('upload')"
              >
                Upload
              </button>
              <button
                class="btn"
                [class.btn-primary]="inputMode() === 'camera'"
                [class.btn-secondary]="inputMode() !== 'camera'"
                (click)="inputMode.set('camera')"
              >
                Camera
              </button>
            </div>

            <app-label-uploader
              *ngIf="inputMode() === 'upload'"
              (fileSelected)="onFileSelected($event)"
            />
            <app-camera-capture
              *ngIf="inputMode() === 'camera'"
              (fileSelected)="onFileSelected($event)"
              (extracted)="onExtracted($event)"
            />
          </div>

          <div style="margin-top:1rem">
            <div *ngIf="error()" class="alert-error">{{ error() }}</div>

            <button
              class="btn btn-primary"
              style="width:100%"
              [disabled]="loading() || !selectedFile() || !appData()"
              (click)="verify()"
            >
              <span *ngIf="loading()" class="spinner"></span>
              {{ loading() ? "Verifying…" : "Verify Label" }}
            </button>

            <p
              *ngIf="!appData() || !selectedFile()"
              style="font-size:0.8125rem;color:var(--text-muted);margin-top:0.5rem;text-align:center"
            >
              {{
                !appData()
                  ? "Save application data first."
                  : "Select a label image."
              }}
            </p>
          </div>
        </div>
      </div>

      <div *ngIf="result()" style="margin-top:1.5rem">
        <app-verification-result [result]="result()"></app-verification-result>
      </div>
    </div>
  `,
})
export class VerifyComponent {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  inputMode = signal<"upload" | "camera">("upload");
  appData = signal<ApplicationData | null>(null);
  selectedFile = signal<File | null>(null);
  loading = signal(false);
  error = signal<string | null>(null);
  result = signal<VerificationResult | null>(null);
  extractedData = signal<ExtractedApplicationData | null>(null);

  onAppDataSaved(data: ApplicationData): void {
    this.appData.set(data);
  }

  onExtracted(data: ExtractedApplicationData): void {
    this.extractedData.set(data);
  }

  onFileSelected(file: File): void {
    this.selectedFile.set(file);
    this.result.set(null);
    this.error.set(null);
  }

  verify(): void {
    const selectedFile = this.selectedFile();
    const appData = this.appData();
    if (!selectedFile || !appData) return;

    this.loading.set(true);
    this.error.set(null);
    this.result.set(null);

    this.api.verify(selectedFile, appData).subscribe({
      next: (r) => {
        this.result.set(r);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        if (err?.status === 401 || err?.status === 403) {
          this.auth.setLoggedIn(false);
          this.router.navigate(["/login"]);
        } else if (err?.status === 429) {
          this.error.set(
            "Rate limit reached. Please wait a moment and try again.",
          );
        } else {
          this.error.set(
            err?.error?.detail ?? "Verification failed. Please try again.",
          );
        }
      },
    });
  }

  logout(): void {
    this.api.logout().subscribe({
      complete: () => {
        this.auth.setLoggedIn(false);
        this.router.navigate(["/login"]);
      },
      error: () => {
        this.auth.setLoggedIn(false);
        this.router.navigate(["/login"]);
      },
    });
  }
}
