import {
  Component,
  Output,
  EventEmitter,
  ViewChild,
  ElementRef,
  OnDestroy,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../../core/services/api.service';
import { ExtractedApplicationData } from '../../../models/label.models';

@Component({
  selector: 'app-camera-capture',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card" style="margin-bottom:0">
      <h3 style="font-size:0.9375rem;font-weight:600;margin-bottom:0.75rem">Camera Capture</h3>

      <div *ngIf="!streaming() && !captured()">
        <button class="btn btn-secondary" (click)="startCamera()">Open Camera</button>
      </div>

      <div *ngIf="error()" class="alert-error" style="margin-top:0.5rem">{{ error() }}</div>

      <!-- Always in the DOM (not gated behind *ngIf="captured()") so capture()
           can read it via ViewChild the moment the user clicks Capture. -->
      <canvas #canvasEl style="display:none"></canvas>

      <div *ngIf="streaming()" style="margin-top:0.75rem">
        <video #videoEl autoplay playsinline style="width:100%;border-radius:0.5rem;border:1px solid var(--border)"></video>
        <div style="display:flex;gap:0.75rem;margin-top:0.75rem">
          <button class="btn btn-primary" (click)="capture()">Capture</button>
          <button class="btn btn-secondary" (click)="stopCamera()">Cancel</button>
        </div>
      </div>

      <div *ngIf="captured()" style="margin-top:0.75rem">
        <img [src]="capturedDataUrl()" alt="Captured" style="width:100%;border-radius:0.5rem;border:1px solid var(--border)" />

        <div *ngIf="extracting()" style="display:flex;align-items:center;gap:0.5rem;margin-top:0.75rem;color:var(--text-muted);font-size:0.875rem">
          <span class="spinner" style="border-color:rgba(37,99,235,0.2);border-top-color:var(--primary)"></span>
          Reading label fields…
        </div>
        <div *ngIf="extractError()" class="alert-warning" style="margin-top:0.75rem">{{ extractError() }}</div>

        <div style="display:flex;gap:0.75rem;margin-top:0.75rem">
          <button class="btn btn-secondary" (click)="retake()">Retake</button>
        </div>
      </div>
    </div>
  `,
})
export class CameraCaptureComponent implements OnDestroy {
  @Output() fileSelected = new EventEmitter<File>();
  @Output() extracted = new EventEmitter<ExtractedApplicationData>();
  @ViewChild('videoEl') videoEl!: ElementRef<HTMLVideoElement>;
  @ViewChild('canvasEl') canvasEl!: ElementRef<HTMLCanvasElement>;

  private readonly api = inject(ApiService);

  streaming = signal(false);
  captured = signal(false);
  capturedDataUrl = signal<string | null>(null);
  error = signal<string | null>(null);
  extracting = signal(false);
  extractError = signal<string | null>(null);

  private stream: MediaStream | null = null;

  async startCamera(): Promise<void> {
    this.error.set(null);
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      this.streaming.set(true);
      // Wait a tick for the video element to render
      setTimeout(() => {
        if (this.videoEl?.nativeElement && this.stream) {
          this.videoEl.nativeElement.srcObject = this.stream;
        }
      }, 0);
    } catch {
      this.error.set('Camera access denied or not available.');
    }
  }

  capture(): void {
    const video = this.videoEl?.nativeElement;
    const canvas = this.canvasEl?.nativeElement;
    if (!video || !canvas) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d')!.drawImage(video, 0, 0);

    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const file = new File([blob], `capture-${Date.now()}.jpg`, {
          type: 'image/jpeg',
        });

        this.capturedDataUrl.set(canvas.toDataURL('image/jpeg'));
        this.streaming.set(false);
        this.captured.set(true);
        this.stopStream();

        // The captured frame becomes the verify-flow's label image
        // immediately, the same way Upload does it — extraction below is a
        // best-effort form accelerator layered on top, not a precondition.
        this.fileSelected.emit(file);
        this.runExtraction(file);
      },
      'image/jpeg',
      0.92,
    );
  }

  private runExtraction(file: File): void {
    this.extracting.set(true);
    this.extractError.set(null);
    this.api.extract(file).subscribe({
      next: (data) => {
        this.extracting.set(false);
        this.extracted.emit(data);
      },
      error: () => {
        this.extracting.set(false);
        this.extractError.set(
          'Could not read fields from photo — enter them manually.',
        );
      },
    });
  }

  retake(): void {
    this.captured.set(false);
    this.capturedDataUrl.set(null);
    this.extractError.set(null);
    this.startCamera();
  }

  stopCamera(): void {
    this.streaming.set(false);
    this.stopStream();
  }

  private stopStream(): void {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }

  ngOnDestroy(): void {
    this.stopStream();
  }
}
