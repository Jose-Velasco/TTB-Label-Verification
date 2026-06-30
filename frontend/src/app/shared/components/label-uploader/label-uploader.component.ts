import { Component, Output, EventEmitter, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const MAX_BYTES = 10 * 1024 * 1024;

@Component({
  selector: 'app-label-uploader',
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
      <p style="font-weight:600">Drop a label image or click to browse</p>
      <p style="font-size:0.8125rem;color:var(--text-muted);margin-top:0.25rem">JPEG, PNG, WebP · max 10 MB</p>
      <input
        #fileInput
        type="file"
        accept="image/jpeg,image/png,image/webp"
        style="display:none"
        (change)="onFileChange($event)"
      />
    </div>

    <div *ngIf="error" class="alert-error" style="margin-top:0.75rem">{{ error }}</div>

    <div *ngIf="preview" style="margin-top:0.75rem;text-align:center">
      <img [src]="preview" alt="Label preview" style="max-width:100%;max-height:300px;border-radius:0.5rem;border:1px solid var(--border)" />
      <p style="font-size:0.8125rem;color:var(--text-muted);margin-top:0.375rem">{{ selectedFile?.name }}</p>
    </div>
  `,
})
export class LabelUploaderComponent {
  @Input() disabled = false;
  @Output() fileSelected = new EventEmitter<File>();

  dragging = false;
  preview: string | null = null;
  selectedFile: File | null = null;
  error: string | null = null;

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
    const file = e.dataTransfer?.files[0];
    if (file) this.processFile(file);
  }

  onFileChange(e: Event): void {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (file) this.processFile(file);
  }

  private processFile(file: File): void {
    this.error = null;

    if (!ALLOWED_TYPES.has(file.type)) {
      this.error = `Unsupported file type: ${file.type}. Use JPEG, PNG, or WebP.`;
      return;
    }

    if (file.size > MAX_BYTES) {
      this.error = `File too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Max 10 MB.`;
      return;
    }

    this.selectedFile = file;
    this.fileSelected.emit(file);

    const reader = new FileReader();
    reader.onload = (ev) => {
      this.preview = ev.target?.result as string;
    };
    reader.readAsDataURL(file);
  }
}
