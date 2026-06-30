import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { VerificationResult, OverallStatus } from '../../../models/label.models';

export interface BatchProgressItem {
  filename: string;
  status: 'pending' | 'done' | 'error';
  result?: VerificationResult;
  error?: string;
}

@Component({
  selector: 'app-batch-progress',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card" *ngIf="total > 0">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem">
        <h3 style="font-size:0.9375rem;font-weight:600">Batch Progress</h3>
        <span style="font-size:0.8125rem;color:var(--text-muted)">{{ done }} / {{ total }}</span>
      </div>

      <div class="progress-bar-wrap" style="margin-bottom:1rem">
        <div class="progress-bar-fill" [style.width.%]="(done / total) * 100"></div>
      </div>

      <ul style="list-style:none;display:grid;gap:0.5rem">
        <li *ngFor="let item of items"
            style="display:flex;align-items:center;justify-content:space-between;font-size:0.875rem">
          <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;margin-right:0.75rem">
            {{ item.filename }}
          </span>
          <ng-container [ngSwitch]="item.status">
            <span *ngSwitchCase="'pending'" style="color:var(--text-muted);flex-shrink:0">
              <span class="spinner" style="width:0.875rem;height:0.875rem;border-color:rgba(0,0,0,.15);border-top-color:var(--primary)"></span>
            </span>
            <span *ngSwitchCase="'done'" [class]="overallBadge(item.result?.overall_status)">
              {{ item.result?.overall_status ?? 'done' }}
            </span>
            <span *ngSwitchCase="'error'" class="badge badge-fail">error</span>
          </ng-container>
        </li>
      </ul>
    </div>
  `,
})
export class BatchProgressComponent {
  @Input() items: BatchProgressItem[] = [];

  get total(): number { return this.items.length; }
  get done(): number { return this.items.filter((i) => i.status !== 'pending').length; }

  overallBadge(status: OverallStatus | undefined): string {
    return status ? `badge badge-${status}` : 'badge';
  }
}
