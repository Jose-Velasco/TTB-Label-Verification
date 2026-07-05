import { Component, Output, EventEmitter, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ApplicationData, ExtractedApplicationData } from '../../../models/label.models';
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

@Component({
  selector: 'app-application-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  template: `
    <div class="card">
      <h2 style="font-size:1.125rem;font-weight:700;margin-bottom:1rem">Application Data</h2>

      <div *ngIf="showAutoFillBanner()" class="alert-warning">
        Fields below were read from the photo. Confirm they match the actual application before verifying.
      </div>

      <form [formGroup]="form" (ngSubmit)="onSubmit()">
        <div class="form-group">
          <label for="brand_name">
            Brand Name
            <span class="badge badge-warning" style="margin-left:0.5rem;text-transform:none;letter-spacing:normal" *ngIf="isUnconfirmed('brand_name')">From photo — verify</span>
          </label>
          <input id="brand_name" type="text" formControlName="brand_name" placeholder="e.g. Stone's Throw" [class.field-unconfirmed]="isUnconfirmed('brand_name')" />
          <span class="error-text" *ngIf="hasError('brand_name')">Required</span>
        </div>
        <div class="form-group">
          <label for="class_type">
            Class / Type
            <span class="badge badge-warning" style="margin-left:0.5rem;text-transform:none;letter-spacing:normal" *ngIf="isUnconfirmed('class_type')">From photo — verify</span>
          </label>
          <input id="class_type" type="text" formControlName="class_type" placeholder="e.g. American Whiskey" [class.field-unconfirmed]="isUnconfirmed('class_type')" />
          <span class="error-text" *ngIf="hasError('class_type')">Required</span>
        </div>
        <div class="form-group">
          <label for="alcohol_content">
            Alcohol Content
            <span class="badge badge-warning" style="margin-left:0.5rem;text-transform:none;letter-spacing:normal" *ngIf="isUnconfirmed('alcohol_content')">From photo — verify</span>
          </label>
          <input id="alcohol_content" type="text" formControlName="alcohol_content" placeholder="e.g. 40% ALC/VOL" [class.field-unconfirmed]="isUnconfirmed('alcohol_content')" />
          <span class="error-text" *ngIf="hasError('alcohol_content')">Required</span>
        </div>
        <div class="form-group">
          <label for="net_contents">
            Net Contents
            <span class="badge badge-warning" style="margin-left:0.5rem;text-transform:none;letter-spacing:normal" *ngIf="isUnconfirmed('net_contents')">From photo — verify</span>
          </label>
          <input id="net_contents" type="text" formControlName="net_contents" placeholder="e.g. 750 mL" [class.field-unconfirmed]="isUnconfirmed('net_contents')" />
          <span class="error-text" *ngIf="hasError('net_contents')">Required</span>
        </div>
        <div class="form-group">
          <label for="bottler_info">
            Bottler Info
            <span class="badge badge-warning" style="margin-left:0.5rem;text-transform:none;letter-spacing:normal" *ngIf="isUnconfirmed('bottler_info')">From photo — verify</span>
          </label>
          <input id="bottler_info" type="text" formControlName="bottler_info" placeholder="e.g. Bottled by Stone's Throw Distillery, Austin TX" [class.field-unconfirmed]="isUnconfirmed('bottler_info')" />
          <span class="error-text" *ngIf="hasError('bottler_info')">Required</span>
        </div>
        <div class="form-group">
          <label for="country_of_origin">
            Country of Origin
            <span class="badge badge-warning" style="margin-left:0.5rem;text-transform:none;letter-spacing:normal" *ngIf="isUnconfirmed('country_of_origin')">From photo — verify</span>
          </label>
          <input id="country_of_origin" type="text" formControlName="country_of_origin" placeholder="e.g. USA" [class.field-unconfirmed]="isUnconfirmed('country_of_origin')" />
          <span class="error-text" *ngIf="hasError('country_of_origin')">Required</span>
        </div>
        <div class="form-group">
          <label for="government_warning">
            Government Warning (expected)
            <span class="badge badge-warning" style="margin-left:0.5rem;text-transform:none;letter-spacing:normal" *ngIf="isUnconfirmed('government_warning')">From photo — verify</span>
          </label>
          <textarea
            id="government_warning"
            formControlName="government_warning"
            rows="4"
            placeholder="GOVERNMENT WARNING: ..."
            [class.field-unconfirmed]="isUnconfirmed('government_warning')"
          ></textarea>
          <span class="error-text" *ngIf="hasError('government_warning')">Required</span>
        </div>
        <button type="submit" class="btn btn-secondary" style="width:100%">
          Save Application Data
        </button>
      </form>
    </div>
  `,
})
export class ApplicationFormComponent implements OnInit {
  @Output() saved = new EventEmitter<ApplicationData>();

  @Input() set autoFill(data: ExtractedApplicationData | null) {
    if (data) this.applyAutoFill(data);
  }

  private readonly fb = inject(FormBuilder);

  form!: FormGroup;
  unconfirmedFields = signal<Set<string>>(new Set());
  showAutoFillBanner = signal(false);

  ngOnInit(): void {
    this.form = this.fb.group({
      brand_name: ['', Validators.required],
      class_type: ['', Validators.required],
      alcohol_content: ['', Validators.required],
      net_contents: ['', Validators.required],
      bottler_info: ['', Validators.required],
      country_of_origin: ['', Validators.required],
      government_warning: [CANONICAL_GOVERNMENT_WARNING, Validators.required],
    });

    // Auto-fill patches use {emitEvent:false} (see applyAutoFill), so only
    // real user edits reach these subscriptions — that's what clears the
    // "unconfirmed" mark for a field.
    for (const name of FIELD_NAMES) {
      this.form.get(name)!.valueChanges.subscribe(() => this.clearUnconfirmed(name));
    }
  }

  hasError(field: string): boolean {
    const ctrl = this.form.get(field);
    return !!ctrl && ctrl.invalid && ctrl.touched;
  }

  isUnconfirmed(field: string): boolean {
    return this.unconfirmedFields().has(field);
  }

  onSubmit(): void {
    this.form.markAllAsTouched();
    if (this.form.valid) {
      this.saved.emit(this.form.value as ApplicationData);
    }
  }

  private applyAutoFill(data: ExtractedApplicationData): void {
    if (!this.form) return;

    const patch: Partial<Record<keyof ApplicationData, string>> = {};
    const next = new Set(this.unconfirmedFields());

    for (const name of FIELD_NAMES) {
      const value = data[name];
      if (value) {
        patch[name] = value;
        next.add(name);
      }
    }

    if (Object.keys(patch).length === 0) return;

    this.form.patchValue(patch, { emitEvent: false });
    this.unconfirmedFields.set(next);
    this.showAutoFillBanner.set(true);
  }

  private clearUnconfirmed(field: string): void {
    if (!this.unconfirmedFields().has(field)) return;
    const next = new Set(this.unconfirmedFields());
    next.delete(field);
    this.unconfirmedFields.set(next);
  }
}
