import { Component, Input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  ExpectedOutcomeStatus,
  FieldResult,
  OverallStatus,
  VerificationResult,
} from '../../../models/label.models';
import { VerificationResultComponent } from '../verification-result/verification-result.component';

export interface BatchProgressItem {
  filename: string;
  status: 'pending' | 'done' | 'error';
  result?: VerificationResult;
  error?: string;
  // Ground truth, present only for stress-test runs (regular batch/verify
  // results have no expected outcome to score against).
  expectedStatus?: ExpectedOutcomeStatus;
  expectedFailingFields?: string[];
  outcomeMatch?: boolean;
}

type FilterMode = 'all' | 'attention' | 'mismatch';

const FIELD_ORDER: (keyof VerificationResult)[] = [
  'brand_name',
  'class_type',
  'alcohol_content',
  'net_contents',
  'bottler_info',
  'country_of_origin',
  'government_warning',
];

@Component({
  selector: 'app-batch-results',
  standalone: true,
  imports: [CommonModule, VerificationResultComponent],
  template: `
    <div class="card batch-summary">
      <div class="batch-summary-counts">
        <span class="batch-summary-count" style="color:var(--pass)">{{ approvedCount }} Approved</span>
        <span class="batch-summary-sep">·</span>
        <span class="batch-summary-count" style="color:var(--fail)">{{ rejectedCount }} Rejected</span>
        <span class="batch-summary-sep">·</span>
        <span class="batch-summary-count" style="color:var(--warning)">{{ needsReviewCount }} Needs Review</span>
        <ng-container *ngIf="avgProcessingTimeSec as avgSec">
          <span class="batch-summary-sep">·</span>
          <span class="batch-summary-avg-time">avg {{ avgSec }}s/label</span>
        </ng-container>
        <ng-container *ngIf="hasGroundTruth">
          <span class="batch-summary-sep">·</span>
          <span
            class="batch-summary-count"
            [style.color]="mismatchCount > 0 ? 'var(--fail)' : 'var(--pass)'"
          >
            {{ matchedCount }}/{{ scoredCount }} matched expected outcome
          </span>
        </ng-container>
      </div>
      <div class="batch-summary-pending" *ngIf="pendingCount > 0">
        <span
          class="spinner"
          style="width:1rem;height:1rem;border-color:rgba(0,0,0,.15);border-top-color:var(--primary)"
        ></span>
        {{ pendingCount }} still processing…
      </div>
    </div>

    <div class="batch-filter" role="group" aria-label="Filter labels">
      <button
        type="button"
        class="batch-filter-btn"
        [class.active]="filterMode() === 'all'"
        (click)="filterMode.set('all')"
      >
        All ({{ items.length }})
      </button>
      <button
        type="button"
        class="batch-filter-btn"
        [class.active]="filterMode() === 'attention'"
        (click)="filterMode.set('attention')"
      >
        Needs Attention ({{ attentionCount }})
      </button>
      <button
        *ngIf="hasGroundTruth"
        type="button"
        class="batch-filter-btn"
        [class.active]="filterMode() === 'mismatch'"
        (click)="filterMode.set('mismatch')"
      >
        Mismatches ({{ mismatchCount }})
      </button>
    </div>

    <div class="batch-row" *ngFor="let item of visibleItems">
      <button
        type="button"
        class="batch-row-header"
        (click)="toggleExpand(item)"
        [attr.aria-expanded]="isExpanded(item)"
      >
        <span class="batch-row-status">
          <span
            *ngIf="item.status === 'pending'"
            class="spinner"
            style="width:1.25rem;height:1.25rem;border-color:rgba(0,0,0,.15);border-top-color:var(--primary)"
          ></span>
          <span *ngIf="item.status === 'done' && item.result?.skipped" class="badge badge-warning">Skipped</span>
          <span
            *ngIf="item.status === 'done' && item.result && !item.result.skipped"
            [class]="'badge badge-' + item.result.overall_status"
          >
            {{ overallStatusLabel(item.result.overall_status) | titlecase }}
          </span>
          <span *ngIf="item.status === 'error'" class="badge badge-fail">Error</span>
          <span *ngIf="item.outcomeMatch === false" class="badge badge-fail">Mismatch</span>
        </span>

        <span class="batch-row-text">
          <span class="batch-row-filename">{{ rowTitle(item) }}</span>
          <span class="batch-row-summary" *ngIf="item.status === 'done' && item.result?.skipped">
            No application data provided for this filename — skipped
          </span>
          <span
            class="batch-row-summary"
            *ngIf="item.status === 'done' && item.result && !item.result.skipped && item.result.overall_status !== 'approved'"
          >
            {{ summaryLine(item.result) }}
          </span>
          <span class="batch-row-summary" *ngIf="item.status === 'error'">
            {{ item.error ?? 'Processing failed' }}
          </span>
          <span class="batch-row-summary" *ngIf="item.outcomeMatch === false" style="color:var(--fail)">
            {{ mismatchDetail(item) }}
          </span>
        </span>

        <span class="batch-row-toggle" *ngIf="item.status === 'done' && item.result">
          {{ isExpanded(item) ? 'Hide details' : 'View details' }}
          <span class="batch-row-chevron" [class.expanded]="isExpanded(item)">›</span>
        </span>
      </button>

      <div class="batch-row-detail" *ngIf="isExpanded(item) && item.result">
        <app-verification-result [result]="item.result" />
      </div>
    </div>
  `,
})
export class BatchResultsComponent {
  @Input() items: BatchProgressItem[] = [];

  filterMode = signal<FilterMode>('all');
  private expandedFilenames = signal<Set<string>>(new Set());

  // Plain getters (not computed signals) on purpose: `items` is a regular
  // @Input() array, not a signal, so a computed() reading it would memoize
  // once and never re-run as new streamed results replace the array —
  // getters re-evaluate on every change-detection pass instead, same
  // pattern the old BatchProgressComponent used for its counts.
  get approvedCount(): number {
    return this.items.filter((i) => i.result?.overall_status === 'approved').length;
  }

  get rejectedCount(): number {
    return this.items.filter((i) => i.result?.overall_status === 'rejected').length;
  }

  get needsReviewCount(): number {
    return this.items.filter((i) => i.result?.overall_status === 'needs_review').length;
  }

  get pendingCount(): number {
    return this.items.filter((i) => i.status === 'pending').length;
  }

  get avgProcessingTimeSec(): string | null {
    const times = this.items
      .map((i) => i.result?.processing_time_ms)
      .filter((ms): ms is number => ms != null);
    if (!times.length) return null;
    const avgMs = times.reduce((sum, ms) => sum + ms, 0) / times.length;
    return (avgMs / 1000).toFixed(1);
  }

  get attentionCount(): number {
    return this.items.filter((i) => this.needsAttention(i)).length;
  }

  // True only for stress-test runs, where every item carries ground truth —
  // regular batch/verify results never set outcomeMatch, so this (and the
  // Mismatches filter/correctness summary it gates) stay hidden for those.
  get hasGroundTruth(): boolean {
    return this.items.some((i) => i.outcomeMatch !== undefined);
  }

  get scoredCount(): number {
    return this.items.filter((i) => i.outcomeMatch !== undefined).length;
  }

  get matchedCount(): number {
    return this.items.filter((i) => i.outcomeMatch === true).length;
  }

  get mismatchCount(): number {
    return this.items.filter((i) => i.outcomeMatch === false).length;
  }

  get visibleItems(): BatchProgressItem[] {
    const mode = this.filterMode();
    const filtered =
      mode === 'all'
        ? this.items
        : mode === 'mismatch'
          ? this.items.filter((i) => i.outcomeMatch === false)
          : this.items.filter((i) => this.needsAttention(i));

    // Triage order: needs-attention first, still-processing next, approved
    // last — stable within each group so arrival order is preserved.
    const rank = (item: BatchProgressItem): number => {
      if (this.needsAttention(item)) return 0;
      if (item.status === 'pending') return 1;
      return 2; // approved
    };
    return filtered
      .map((item, index) => ({ item, index }))
      .sort((a, b) => rank(a.item) - rank(b.item) || a.index - b.index)
      .map((x) => x.item);
  }

  toggleExpand(item: BatchProgressItem): void {
    const next = new Set(this.expandedFilenames());
    if (next.has(item.filename)) next.delete(item.filename);
    else next.add(item.filename);
    this.expandedFilenames.set(next);
  }

  isExpanded(item: BatchProgressItem): boolean {
    return this.expandedFilenames().has(item.filename);
  }

  rowTitle(item: BatchProgressItem): string {
    const brand = item.result && !item.result.skipped ? item.result.brand_name.expected_value : '';
    return brand ? `${brand} — ${item.filename}` : item.filename;
  }

  overallStatusLabel(status: OverallStatus): string {
    // Same fix as VerificationResultComponent: "needs_review" has no word
    // boundary for `| titlecase`, so replace the underscore before piping.
    return status.replace(/_/g, ' ');
  }

  summaryLine(result: VerificationResult): string {
    const failing = FIELD_ORDER.filter((k) => (result[k] as FieldResult).status !== 'pass');
    if (!failing.length) return '';

    const firstKey = failing[0];
    const label = this.fieldLabel(firstKey);
    if (failing.length === 1) {
      return `${label} ${this.statusVerb((result[firstKey] as FieldResult).status)}`;
    }

    const rest = failing.length - 1;
    return `${label} and ${rest} other${rest > 1 ? 's' : ''} don't match`;
  }

  private needsAttention(item: BatchProgressItem): boolean {
    // outcomeMatch === false also flags a "false approve": the model said
    // approved but ground truth expected a rejection (or vice versa), which
    // result.overall_status alone wouldn't surface as needing a look.
    return (
      item.status === 'error' ||
      item.outcomeMatch === false ||
      (item.status === 'done' && item.result?.overall_status !== 'approved')
    );
  }

  mismatchDetail(item: BatchProgressItem): string {
    if (item.outcomeMatch !== false) return '';
    const expected =
      item.expectedStatus === 'rejected' && item.expectedFailingFields?.length
        ? `rejected (${item.expectedFailingFields.join(', ')} expected to fail)`
        : item.expectedStatus;
    const actual = item.result?.skipped ? 'skipped' : (item.result?.overall_status ?? 'unknown');
    return `Ground truth mismatch — expected ${expected}, got ${actual}`;
  }

  private fieldLabel(key: keyof VerificationResult): string {
    const spaced = key.replace(/_/g, ' ');
    return spaced.charAt(0).toUpperCase() + spaced.slice(1);
  }

  private statusVerb(status: string): string {
    switch (status) {
      case 'fail':
        return 'mismatch';
      case 'warning':
        return 'uncertain match';
      case 'unreadable':
        return 'unreadable';
      default:
        return 'issue';
    }
  }
}
