import { Component, Output, EventEmitter, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ApplicationData } from '../../../models/label.models';
import { CANONICAL_GOVERNMENT_WARNING } from '../../../core/services/validation.service';

@Component({
  selector: 'app-application-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  template: `
    <div class="card">
      <h2 style="font-size:1.125rem;font-weight:700;margin-bottom:1rem">Application Data</h2>
      <form [formGroup]="form" (ngSubmit)="onSubmit()">
        <div class="form-group">
          <label for="brand_name">Brand Name</label>
          <input id="brand_name" type="text" formControlName="brand_name" placeholder="e.g. Stone's Throw" />
          <span class="error-text" *ngIf="hasError('brand_name')">Required</span>
        </div>
        <div class="form-group">
          <label for="class_type">Class / Type</label>
          <input id="class_type" type="text" formControlName="class_type" placeholder="e.g. American Whiskey" />
          <span class="error-text" *ngIf="hasError('class_type')">Required</span>
        </div>
        <div class="form-group">
          <label for="alcohol_content">Alcohol Content</label>
          <input id="alcohol_content" type="text" formControlName="alcohol_content" placeholder="e.g. 40% ALC/VOL" />
          <span class="error-text" *ngIf="hasError('alcohol_content')">Required</span>
        </div>
        <div class="form-group">
          <label for="net_contents">Net Contents</label>
          <input id="net_contents" type="text" formControlName="net_contents" placeholder="e.g. 750 mL" />
          <span class="error-text" *ngIf="hasError('net_contents')">Required</span>
        </div>
        <div class="form-group">
          <label for="bottler_info">Bottler Info</label>
          <input id="bottler_info" type="text" formControlName="bottler_info" placeholder="e.g. Bottled by Stone's Throw Distillery, Austin TX" />
          <span class="error-text" *ngIf="hasError('bottler_info')">Required</span>
        </div>
        <div class="form-group">
          <label for="country_of_origin">Country of Origin</label>
          <input id="country_of_origin" type="text" formControlName="country_of_origin" placeholder="e.g. USA" />
          <span class="error-text" *ngIf="hasError('country_of_origin')">Required</span>
        </div>
        <div class="form-group">
          <label for="government_warning">Government Warning (expected)</label>
          <textarea
            id="government_warning"
            formControlName="government_warning"
            rows="4"
            placeholder="GOVERNMENT WARNING: ..."
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

  private readonly fb = inject(FormBuilder);

  form!: FormGroup;

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
  }

  hasError(field: string): boolean {
    const ctrl = this.form.get(field);
    return !!ctrl && ctrl.invalid && ctrl.touched;
  }

  onSubmit(): void {
    this.form.markAllAsTouched();
    if (this.form.valid) {
      this.saved.emit(this.form.value as ApplicationData);
    }
  }
}
