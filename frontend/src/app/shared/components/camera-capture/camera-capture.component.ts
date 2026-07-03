import {
  Component,
  Output,
  EventEmitter,
  ViewChild,
  ElementRef,
  OnDestroy,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';

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

      <div *ngIf="streaming()" style="margin-top:0.75rem">
        <video #videoEl autoplay playsinline style="width:100%;border-radius:0.5rem;border:1px solid var(--border)"></video>
        <div style="display:flex;gap:0.75rem;margin-top:0.75rem">
          <button class="btn btn-primary" (click)="capture()">Capture</button>
          <button class="btn btn-secondary" (click)="stopCamera()">Cancel</button>
        </div>
      </div>

      <div *ngIf="captured()" style="margin-top:0.75rem">
        <canvas #canvasEl style="display:none"></canvas>
        <img [src]="capturedDataUrl()" alt="Captured" style="width:100%;border-radius:0.5rem;border:1px solid var(--border)" />
        <div style="display:flex;gap:0.75rem;margin-top:0.75rem">
          <button class="btn btn-primary" (click)="useCapture()">Use This Photo</button>
          <button class="btn btn-secondary" (click)="retake()">Retake</button>
        </div>
      </div>
    </div>
  `,
})
export class CameraCaptureComponent implements OnDestroy {
  @Output() fileSelected = new EventEmitter<File>();
  @ViewChild('videoEl') videoEl!: ElementRef<HTMLVideoElement>;
  @ViewChild('canvasEl') canvasEl!: ElementRef<HTMLCanvasElement>;

  streaming = signal(false);
  captured = signal(false);
  capturedDataUrl = signal<string | null>(null);
  error = signal<string | null>(null);

  private stream: MediaStream | null = null;
  private capturedBlob: Blob | null = null;

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
        this.capturedBlob = blob;
        this.capturedDataUrl.set(canvas.toDataURL('image/jpeg'));
        this.streaming.set(false);
        this.captured.set(true);
        this.stopStream();
      },
      'image/jpeg',
      0.92,
    );
  }

  useCapture(): void {
    if (!this.capturedBlob) return;
    const file = new File([this.capturedBlob], `capture-${Date.now()}.jpg`, {
      type: 'image/jpeg',
    });
    this.fileSelected.emit(file);
  }

  retake(): void {
    this.captured.set(false);
    this.capturedDataUrl.set(null);
    this.capturedBlob = null;
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
