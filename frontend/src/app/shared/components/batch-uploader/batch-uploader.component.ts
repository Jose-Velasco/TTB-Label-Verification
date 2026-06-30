import { Component, Output, EventEmitter, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const MAX_BYTES = 10 * 1024 * 1024;

@Component({
  selector: 'app-batch-uploader',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div
      class="drop-zone"
      [class.dragging]="dragging"
      (dragover)="onDragOver($event)"
      (dragleave)="onDragLeave()"
      (drop)="onDrop($event)"
      (click)="fileInput.click()"
    >
      <p style="font-size:1.25rem;margin-bottom:0.5rem">📂</p>
      <p style="font-weight:600">Drop label images or click to browse</p>
      <p style="font-size:0.8125rem;color:var(--text-muted);margin-top:0.25rem">
        Multiple files · JPEG, PNG, WebP · max 10 MB each
      </p>
      <input
        #fileInput
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        style="display:none"
        (change)="onFileChange($event)"
      />
    </div>

    <div *ngFor="let e of errors" class="alert-error" style="margin-top:0.5rem">{{ e }}</div>

    <div *ngIf="files.length" style="margin-top:0.75rem">
      <p style="font-size:0.875rem;font-weight:600;margin-bottom:0.5rem">
        {{ files.length }} file{{ files.length === 1 ? '' : 's' }} selected
      </p>
      <ul style="list-style:none;display:grid;gap:0.375rem">
        <li *ngFor="let f of files; let i = index"
            style="font-size:0.8125rem;color:var(--text-muted);display:flex;justify-content:space-between;align-items:center;background:var(--bg);padding:0.375rem 0.625rem;border-radius:0.375rem">
          <span>{{ f.name }}</span>
          <button
            style="background:none;border:none;cursor:pointer;color:var(--fail);font-size:1rem;line-height:1"
            (click)="remove(i)"
            title="Remove"
          >×</button>
        </li>
      </ul>
    </div>
  `,
})
export class BatchUploaderComponent {
  @Input() disabled = false;
  @Output() filesSelected = new EventEmitter<File[]>();

  dragging = false;
  files: File[] = [];
  errors: string[] = [];

  onDragOver(e: DragEvent): void {
    e.preventDefault();
    this.dragging = true;
  }

  onDragLeave(): void {
    this.dragging = false;
  }

  onDrop(e: DragEvent): void {
    e.preventDefault();
    this.dragging = false;
    const incoming = Array.from(e.dataTransfer?.files ?? []);
    this.processFiles(incoming);
  }

  onFileChange(e: Event): void {
    const incoming = Array.from((e.target as HTMLInputElement).files ?? []);
    this.processFiles(incoming);
  }

  remove(index: number): void {
    this.files.splice(index, 1);
    this.filesSelected.emit([...this.files]);
  }

  private processFiles(incoming: File[]): void {
    this.errors = [];
    const valid: File[] = [];

    for (const f of incoming) {
      if (!ALLOWED_TYPES.has(f.type)) {
        this.errors.push(`${f.name}: unsupported type ${f.type}`);
        continue;
      }
      if (f.size > MAX_BYTES) {
        this.errors.push(`${f.name}: too large (${(f.size / 1024 / 1024).toFixed(1)} MB)`);
        continue;
      }
      valid.push(f);
    }

    this.files = [...this.files, ...valid];
    this.filesSelected.emit([...this.files]);
  }
}
