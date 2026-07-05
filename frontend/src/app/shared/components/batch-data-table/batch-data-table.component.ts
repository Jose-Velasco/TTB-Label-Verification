import { Component, EventEmitter, Input, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import Papa from 'papaparse';
import { ApplicationData } from '../../../models/label.models';
import { CANONICAL_GOVERNMENT_WARNING } from '../../../core/services/validation.service';

const FIELD_NAMES: (keyof ApplicationData)[] = [
  'brand_name',
  'class_type',
  'alcohol_content',
  'net_contents',
  'bottler_info',
  'country_of_origin',
  'government_warning',
];

const FIELD_LABELS: Record<keyof ApplicationData, string> = {
  brand_name: 'Brand Name',
  class_type: 'Class / Type',
  alcohol_content: 'Alcohol Content',
  net_contents: 'Net Contents',
  bottler_info: 'Bottler Info',
  country_of_origin: 'Country of Origin',
  government_warning: 'Government Warning',
};

export interface BatchRow {
  filename: string;
  fields: ApplicationData;
  unconfirmedFields: Set<keyof ApplicationData>;
  complete: boolean;
}

interface CsvEntry {
  filename: string; // original casing, for display
  fields: Partial<Record<keyof ApplicationData, string>>;
}

function blankFields(): ApplicationData {
  return {
    brand_name: '',
    class_type: '',
    alcohol_content: '',
    net_contents: '',
    bottler_info: '',
    country_of_origin: '',
    government_warning: CANONICAL_GOVERNMENT_WARNING,
  };
}

function isComplete(fields: ApplicationData): boolean {
  return FIELD_NAMES.every((k) => fields[k].trim() !== '');
}

@Component({
  selector: 'app-batch-data-table',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div>
      <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap">
        <button type="button" class="btn btn-secondary" (click)="csvInput.click()">Import CSV</button>
        <input
          #csvInput
          type="file"
          accept=".csv,text/csv"
          style="display:none"
          (change)="onCsvSelected($event)"
        />
        <span *ngIf="rows().length" style="font-size:0.8125rem;color:var(--text-muted)">
          {{ completeCount() }} of {{ rows().length }} images ready
        </span>
      </div>

      <div *ngIf="csvError()" class="alert-error" style="margin-top:0.75rem">{{ csvError() }}</div>
      <div *ngIf="unmatchedCsvFilenames().length" class="alert-warning" style="margin-top:0.75rem">
        {{ unmatchedCsvFilenames().length }} CSV row(s) had no matching uploaded image and were skipped:
        {{ unmatchedCsvFilenames().join(', ') }}
      </div>

      <p *ngIf="rows().length" style="font-size:0.8125rem;color:var(--text-muted);margin-top:0.75rem">
        Amber fields were imported from CSV — review before running. Rows with any blank field are
        excluded from the batch run (skipped, not failed).
      </p>

      <div class="batch-data-table-wrap" *ngIf="rows().length">
        <table class="batch-data-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Filename</th>
              <th *ngFor="let key of fieldNames">{{ fieldLabel(key) }}</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let row of rows()" [class.row-incomplete]="!row.complete">
              <td>
                <span class="badge" [class.badge-pass]="row.complete" [class.badge-warning]="!row.complete">
                  {{ row.complete ? 'Ready' : 'Incomplete' }}
                </span>
              </td>
              <td style="font-weight:600;white-space:nowrap">{{ row.filename }}</td>
              <td *ngFor="let key of fieldNames">
                <input
                  type="text"
                  [value]="row.fields[key]"
                  (input)="onFieldEdit(row, key, $any($event.target).value)"
                  [class.field-unconfirmed]="isUnconfirmed(row, key)"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p *ngIf="!rows().length" style="font-size:0.8125rem;color:var(--text-muted)">
        Upload label images to enter their application data here.
      </p>
    </div>
  `,
})
export class BatchDataTableComponent {
  @Output() rowsChange = new EventEmitter<BatchRow[]>();

  @Input() set files(value: File[]) {
    this.syncRows(value ?? []);
  }

  readonly fieldNames = FIELD_NAMES;

  rows = signal<BatchRow[]>([]);
  csvError = signal<string | null>(null);
  unmatchedCsvFilenames = signal<string[]>([]);

  private rowsByFilename = new Map<string, BatchRow>();

  // Last-imported CSV, kept around (not just applied once) so that images
  // uploaded AFTER the CSV — in any order, including interleaved — still get
  // matched against it once they appear.
  private csvByFilename = new Map<string, CsvEntry>();
  private csvDuplicateNames: string[] = [];
  // Filenames that already received the CURRENT csvByFilename's values, so
  // reconciling after an unrelated file-list change doesn't clobber a row the
  // user has since edited by hand. Reset whenever a new CSV is imported, so
  // re-importing intentionally overwrites matched rows again.
  private csvAppliedTo = new Set<string>();

  fieldLabel(key: keyof ApplicationData): string {
    return FIELD_LABELS[key];
  }

  isUnconfirmed(row: BatchRow, key: keyof ApplicationData): boolean {
    return row.unconfirmedFields.has(key);
  }

  completeCount(): number {
    return this.rows().filter((r) => r.complete).length;
  }

  onFieldEdit(row: BatchRow, key: keyof ApplicationData, value: string): void {
    row.fields = { ...row.fields, [key]: value };
    row.unconfirmedFields.delete(key);
    row.complete = isComplete(row.fields);
    this.emitRows();
  }

  onCsvSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = ''; // allow re-selecting the same file after fixing it
    if (!file) return;

    this.csvError.set(null);
    this.unmatchedCsvFilenames.set([]);

    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      transformHeader: (h) => h.trim().toLowerCase(),
      complete: (results) => this.applyCsv(results.data),
      error: (err) => this.csvError.set(`Could not read CSV: ${err.message}`),
    });
  }

  private applyCsv(csvRows: Record<string, string>[]): void {
    if (!csvRows.length) {
      this.csvError.set('CSV file has no data rows.');
      return;
    }
    if (!('filename' in csvRows[0])) {
      this.csvError.set('CSV must have a "filename" column.');
      return;
    }

    const next = new Map<string, CsvEntry>();
    const duplicates: string[] = [];

    for (const csvRow of csvRows) {
      const rawFilename = (csvRow['filename'] ?? '').trim();
      if (!rawFilename) continue;
      const key = rawFilename.toLowerCase();

      if (next.has(key)) {
        duplicates.push(rawFilename);
        continue;
      }

      const fields: Partial<Record<keyof ApplicationData, string>> = {};
      for (const fieldName of FIELD_NAMES) {
        const value = (csvRow[fieldName] ?? '').trim();
        if (value) fields[fieldName] = value;
      }
      next.set(key, { filename: rawFilename, fields });
    }

    this.csvByFilename = next;
    this.csvDuplicateNames = duplicates;
    // A fresh import re-matches everything currently uploaded, even rows an
    // earlier import already touched.
    this.csvAppliedTo = new Set();

    this.reconcile();
  }

  private syncRows(files: File[]): void {
    const next: BatchRow[] = [];
    const seenLower = new Set<string>();

    for (const f of files) {
      const key = f.name.toLowerCase();
      seenLower.add(key);
      let row = this.rowsByFilename.get(key);
      if (!row) {
        row = {
          filename: f.name,
          fields: blankFields(),
          unconfirmedFields: new Set(),
          complete: false,
        };
        row.complete = isComplete(row.fields);
        this.rowsByFilename.set(key, row);
      }
      next.push(row);
    }

    for (const key of Array.from(this.rowsByFilename.keys())) {
      if (!seenLower.has(key)) {
        this.rowsByFilename.delete(key);
        // If this filename is re-added later, let CSV data (if still pending
        // for it) re-apply to the fresh row rather than staying skipped.
        this.csvAppliedTo.delete(key);
      }
    }

    this.rows.set(next);
    this.reconcile();
  }

  /** Re-derives CSV <-> image matches from current state. Called whenever
   * EITHER side changes (file list or imported CSV) so the two can be
   * populated in any order, including interleaved. */
  private reconcile(): void {
    for (const [key, entry] of this.csvByFilename) {
      if (this.csvAppliedTo.has(key)) continue;
      const row = this.rowsByFilename.get(key);
      if (!row) continue; // no matching image yet — stays pending

      const updatedFields = { ...row.fields };
      const updatedUnconfirmed = new Set(row.unconfirmedFields);
      for (const fieldName of FIELD_NAMES) {
        const value = entry.fields[fieldName];
        if (value) {
          updatedFields[fieldName] = value;
          updatedUnconfirmed.add(fieldName);
        }
      }
      row.fields = updatedFields;
      row.unconfirmedFields = updatedUnconfirmed;
      row.complete = isComplete(row.fields);
      this.csvAppliedTo.add(key);
    }

    const unmatched = Array.from(this.csvByFilename.entries())
      .filter(([key]) => !this.rowsByFilename.has(key))
      .map(([, entry]) => entry.filename);

    this.unmatchedCsvFilenames.set([
      ...unmatched,
      ...this.csvDuplicateNames.map((d) => `${d} (duplicate row)`),
    ]);
    this.emitRows();
  }

  private emitRows(): void {
    this.rows.set([...this.rows()]);
    this.rowsChange.emit(this.rows());
  }
}
