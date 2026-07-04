import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { VerificationResult, FieldResult, FieldStatus, OverallStatus } from '../../../models/label.models';

@Component({
  selector: 'app-verification-result',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card" *ngIf="result">
      <div class="page-header" style="margin-bottom:1rem">
        <div>
          <h2 style="font-size:1.125rem;font-weight:700;margin-bottom:0.25rem">
            {{ result.filename ?? 'Label' }}
          </h2>
          <p style="font-size:0.8125rem;color:var(--text-muted)" *ngIf="result.processing_time_ms != null">
            Processed in {{ result.processing_time_ms }}ms
          </p>
        </div>
        <span [class]="overallBadgeClass(result.overall_status)">
          {{ overallStatusLabel(result.overall_status) | titlecase }}
        </span>
      </div>

      <div *ngIf="result.image_quality_note" class="alert-warning" style="margin-bottom:1rem">
        {{ result.image_quality_note }}
      </div>

      <div style="display:grid;gap:0.75rem">
        <ng-container *ngFor="let field of fieldEntries">
          <div style="border:1px solid var(--border);border-radius:0.5rem;padding:0.875rem">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.375rem">
              <span style="font-size:0.8125rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-muted)">
                {{ fieldLabel(field.key) }}
              </span>
              <span [class]="fieldBadgeClass(field.result.status)">{{ field.result.status }}</span>
            </div>
            <p style="font-size:0.875rem;margin-bottom:0.25rem">
              <span style="color:var(--text-muted)">Extracted: </span>
              <span style="font-family:monospace">{{ field.result.extracted_value ?? '—' }}</span>
            </p>
            <p style="font-size:0.875rem;margin-bottom:0.25rem">
              <span style="color:var(--text-muted)">Expected: </span>
              <span style="font-family:monospace">{{ field.result.expected_value }}</span>
            </p>
            <p *ngIf="field.result.note" style="font-size:0.8125rem;color:var(--text-muted);margin-top:0.25rem;font-style:italic">
              {{ field.result.note }}
            </p>
          </div>
        </ng-container>
      </div>
    </div>
  `,
})
export class VerificationResultComponent {
  @Input() result: VerificationResult | null = null;

  readonly fieldKeys: (keyof VerificationResult)[] = [
    'brand_name', 'class_type', 'alcohol_content',
    'net_contents', 'bottler_info', 'country_of_origin', 'government_warning',
  ];

  get fieldEntries(): { key: keyof VerificationResult; result: FieldResult }[] {
    if (!this.result) return [];
    return this.fieldKeys.map((k) => ({
      key: k,
      result: this.result![k] as FieldResult,
    }));
  }

  fieldLabel(key: keyof VerificationResult): string {
    return key.replace(/_/g, ' ');
  }

  fieldBadgeClass(status: FieldStatus): string {
    return `badge badge-${status}`;
  }

  overallBadgeClass(status: OverallStatus): string {
    return `badge badge-${status}`;
  }

  overallStatusLabel(status: OverallStatus): string {
    // "needs_review" has no word boundary for `| titlecase` to find, so it
    // renders as "Needs_review" (then "NEEDS_REVIEW" under the badge's
    // uppercase styling) without this — replace the underscore first.
    return status.replace(/_/g, ' ');
  }
}
