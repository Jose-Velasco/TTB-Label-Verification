import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive, Router } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { ApplicationData } from '../../models/label.models';
import { ApplicationFormComponent } from '../../shared/components/application-form/application-form.component';
import { BatchUploaderComponent } from '../../shared/components/batch-uploader/batch-uploader.component';
import { BatchProgressComponent, BatchProgressItem } from '../../shared/components/batch-progress/batch-progress.component';
import { VerificationResultComponent } from '../../shared/components/verification-result/verification-result.component';

@Component({
  selector: 'app-batch',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    RouterLinkActive,
    ApplicationFormComponent,
    BatchUploaderComponent,
    BatchProgressComponent,
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
          <h1>Batch Verification</h1>
          <p>Upload multiple label images to verify simultaneously.</p>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem">
        <div>
          <app-application-form (saved)="onAppDataSaved($event)" />
        </div>

        <div>
          <div class="card">
            <h2 style="font-size:1.125rem;font-weight:700;margin-bottom:1rem">Label Images</h2>
            <app-batch-uploader
              [disabled]="loading()"
              (filesSelected)="onFilesSelected($event)"
            />
          </div>

          <div style="margin-top:1rem">
            <div *ngIf="error()" class="alert-error">{{ error() }}</div>

            <button
              class="btn btn-primary"
              style="width:100%"
              [disabled]="loading() || !files().length || !appData()"
              (click)="runBatch()"
            >
              <span *ngIf="loading()" class="spinner"></span>
              {{ loading() ? 'Processing…' : 'Start Batch (' + files().length + ' files)' }}
            </button>

            <p *ngIf="!appData() || !files().length" style="font-size:0.8125rem;color:var(--text-muted);margin-top:0.5rem;text-align:center">
              {{ !appData() ? 'Save application data first.' : 'Select at least one label image.' }}
            </p>
          </div>
        </div>
      </div>

      <div style="margin-top:1.5rem" *ngIf="progressItems().length">
        <app-batch-progress [items]="progressItems()" />
      </div>

      <div style="margin-top:1rem" *ngFor="let item of progressItems()">
        <app-verification-result *ngIf="item.result" [result]="item.result" />
        <div *ngIf="item.error" class="alert-error">{{ item.filename }}: {{ item.error }}</div>
      </div>
    </div>
  `,
})
export class BatchComponent {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  appData = signal<ApplicationData | null>(null);
  files = signal<File[]>([]);
  loading = signal(false);
  error = signal<string | null>(null);
  progressItems = signal<BatchProgressItem[]>([]);

  onAppDataSaved(data: ApplicationData): void {
    this.appData.set(data);
  }

  onFilesSelected(files: File[]): void {
    this.files.set(files);
  }

  runBatch(): void {
    const files = this.files();
    const appData = this.appData();
    if (!files.length || !appData) return;

    this.loading.set(true);
    this.error.set(null);

    this.progressItems.set(
      files.map((f) => ({
        filename: f.name,
        status: 'pending' as const,
      })),
    );

    this.api.verifyBatch(files, appData).subscribe({
      next: (result) => {
        this.progressItems.update((items) => {
          const idx = items.findIndex((item) => item.filename === result.filename);
          const target = idx >= 0 ? idx : items.findIndex((i) => i.status === 'pending');
          if (target < 0) return items;
          const next = items.slice();
          next[target] = {
            filename: result.filename ?? items[target].filename,
            status: 'done',
            result,
          };
          return next;
        });
      },
      error: (err) => {
        this.loading.set(false);
        if (err?.status === 401 || err?.status === 403) {
          this.auth.setLoggedIn(false);
          this.router.navigate(['/login']);
        } else if (err?.status === 429) {
          this.error.set('Rate limit reached. Please wait a moment and try again.');
        } else {
          this.error.set(err?.message ?? 'Batch processing failed.');
        }
        // Mark remaining pending items as error
        this.progressItems.update((items) =>
          items.map((item) =>
            item.status === 'pending' ? { ...item, status: 'error', error: 'Aborted' } : item,
          ),
        );
      },
      complete: () => {
        this.loading.set(false);
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
