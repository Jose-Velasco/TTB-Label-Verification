import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive, Router } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { StressTestEstimate } from '../../models/label.models';
import { BatchResultsComponent, BatchProgressItem } from '../../shared/components/batch-results/batch-results.component';

const MIN_COUNT = 20;
const MAX_COUNT = 100;
// Confirm above this many images (real API cost); at or below it, running
// straight away is cheap/fast enough that a prompt would just be friction.
const CONFIRMATION_THRESHOLD = 20;

@Component({
  selector: 'app-stress-test',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, BatchResultsComponent],
  template: `
    <div class="container">
      <nav class="nav">
        <a routerLink="/verify" routerLinkActive="active">Single Verify</a>
        <a routerLink="/batch" routerLinkActive="active">Batch</a>
        <a routerLink="/stress-test" routerLinkActive="active">Stress Test</a>
        <button class="btn btn-secondary" style="margin-left:auto;padding:0.375rem 0.875rem;font-size:0.8125rem" (click)="logout()">
          Sign Out
        </button>
      </nav>

      <div class="page-header">
        <div>
          <h1>Stress Test</h1>
          <p>Generate synthetic label images and run them through real batch verification.</p>
        </div>
      </div>

      <div class="card">
        <h2 style="font-size:1.125rem;font-weight:700;margin-bottom:1rem">Images to generate</h2>
        <div style="display:flex;align-items:center;gap:1rem">
          <input
            type="range"
            [min]="minCount"
            [max]="maxCount"
            [value]="count()"
            (input)="onCountChange($any($event.target).value)"
            [disabled]="loading() || confirming()"
            style="flex:1"
          />
          <span style="font-weight:700;font-size:1.25rem;min-width:3ch;text-align:right">{{ count() }}</span>
        </div>
        <p style="font-size:0.8125rem;color:var(--text-muted);margin-top:0.5rem">
          A couple of the generated images are deliberately left out of the application data, so
          the run also exercises the "no data provided — skipped" path, not just pass/fail outcomes.
        </p>

        <button
          class="btn btn-primary"
          style="width:100%;margin-top:1rem"
          [disabled]="loading() || confirming()"
          (click)="clickGenerateAndRun()"
        >
          <span *ngIf="loading()" class="spinner"></span>
          {{ loading() ? 'Running…' : 'Generate & Run (' + count() + ')' }}
        </button>
      </div>

      <div class="card" *ngIf="confirming()">
        <h2 style="font-size:1.125rem;font-weight:700;margin-bottom:0.75rem">Confirm before running</h2>

        <div
          *ngIf="estimating()"
          style="display:flex;align-items:center;gap:0.5rem;color:var(--text-muted);font-size:0.9375rem"
        >
          <span class="spinner" style="width:1rem;height:1rem;border-color:rgba(0,0,0,.15);border-top-color:var(--primary)"></span>
          Estimating cost and time…
        </div>

        <div *ngIf="estimateError()" class="alert-error">{{ estimateError() }}</div>

        <div *ngIf="estimate() as est">
          <p style="font-size:0.9375rem">
            This will make <strong>~{{ est.real_call_count }}</strong> real vision-model calls
            (out of {{ est.count }} generated images).
          </p>
          <p style="font-size:0.9375rem;margin-top:0.5rem">
            Estimated cost: <strong>{{ formatCost(est.estimated_cost_usd) }}</strong>
            &nbsp;·&nbsp;
            Estimated time: <strong>~{{ formatDuration(est.estimated_seconds) }}</strong>
          </p>
          <div style="display:flex;gap:0.75rem;margin-top:1rem">
            <button class="btn btn-primary" (click)="confirmAndRun()">Run {{ est.count }} images</button>
            <button class="btn btn-secondary" (click)="cancelConfirmation()">Cancel</button>
          </div>
        </div>
      </div>

      <div *ngIf="error()" class="alert-error">{{ error() }}</div>

      <div style="margin-top:1.5rem" *ngIf="progressItems().length">
        <app-batch-results [items]="progressItems()" />
      </div>
    </div>
  `,
})
export class StressTestComponent {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly minCount = MIN_COUNT;
  readonly maxCount = MAX_COUNT;

  count = signal(MIN_COUNT);
  loading = signal(false);
  error = signal<string | null>(null);
  progressItems = signal<BatchProgressItem[]>([]);

  confirming = signal(false);
  estimating = signal(false);
  estimateError = signal<string | null>(null);
  estimate = signal<StressTestEstimate | null>(null);

  onCountChange(value: string): void {
    const parsed = Math.round(Number(value));
    const n = Number.isFinite(parsed) ? parsed : this.minCount;
    this.count.set(Math.min(this.maxCount, Math.max(this.minCount, n)));
  }

  clickGenerateAndRun(): void {
    if (this.count() > CONFIRMATION_THRESHOLD) {
      this.startConfirmation();
    } else {
      this.runStressTest();
    }
  }

  cancelConfirmation(): void {
    this.confirming.set(false);
    this.estimate.set(null);
    this.estimateError.set(null);
  }

  confirmAndRun(): void {
    this.confirming.set(false);
    this.runStressTest();
  }

  formatCost(cost: number | null): string {
    if (cost === null) return 'not available for this provider';
    if (cost < 0.01) return '< $0.01';
    return `~$${cost.toFixed(2)}`;
  }

  formatDuration(seconds: number): string {
    const minutes = seconds / 60;
    return minutes < 1 ? `${Math.ceil(seconds)}s` : `${minutes.toFixed(1)} min`;
  }

  private startConfirmation(): void {
    this.confirming.set(true);
    this.estimating.set(true);
    this.estimateError.set(null);
    this.estimate.set(null);

    this.api.estimateStressTest(this.count()).subscribe({
      next: (est) => {
        this.estimating.set(false);
        this.estimate.set(est);
      },
      error: (err) => {
        this.estimating.set(false);
        this.estimateError.set(err?.message ?? 'Could not estimate cost/time.');
      },
    });
  }

  private runStressTest(): void {
    const n = this.count();
    this.loading.set(true);
    this.error.set(null);

    // Filenames aren't known upfront (generated server-side) — seed generic
    // pending placeholders and let each streamed result fill the next open
    // slot, the same fallback-by-position matching BatchComponent uses.
    this.progressItems.set(
      Array.from({ length: n }, (_, i) => ({
        filename: `Generated image ${i + 1}`,
        status: 'pending' as const,
      })),
    );

    this.api.runStressTest(n).subscribe({
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
          this.error.set(err?.message ?? 'Stress test failed.');
        }
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
