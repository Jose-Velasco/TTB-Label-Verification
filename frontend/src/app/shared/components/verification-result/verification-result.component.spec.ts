import { TestBed, ComponentFixture } from '@angular/core/testing';
import { VerificationResultComponent } from './verification-result.component';
import { VerificationResult } from '../../../models/label.models';

const mockResult: VerificationResult = {
  overall_status: 'approved',
  brand_name: { status: 'pass', extracted_value: "Stone's Throw", expected_value: "Stone's Throw", note: null },
  class_type: { status: 'pass', extracted_value: 'American Whiskey', expected_value: 'American Whiskey', note: null },
  alcohol_content: { status: 'pass', extracted_value: '40% ALC/VOL', expected_value: '40% ALC/VOL', note: null },
  net_contents: { status: 'pass', extracted_value: '750 mL', expected_value: '750 mL', note: null },
  bottler_info: { status: 'pass', extracted_value: "Stone's Throw Distillery", expected_value: "Stone's Throw Distillery", note: null },
  country_of_origin: { status: 'pass', extracted_value: 'USA', expected_value: 'USA', note: null },
  government_warning: {
    status: 'pass',
    extracted_value: 'GOVERNMENT WARNING: ...',
    expected_value: 'GOVERNMENT WARNING: ...',
    note: null,
  },
  processing_time_ms: 1234,
  image_quality_note: null,
  filename: 'test_label.jpg',
};

describe('VerificationResultComponent', () => {
  let fixture: ComponentFixture<VerificationResultComponent>;
  let component: VerificationResultComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [VerificationResultComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(VerificationResultComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('has no fieldEntries when result is null', () => {
    expect(component.fieldEntries.length).toBe(0);
  });

  it('returns 7 fieldEntries when result is set', () => {
    component.result = mockResult;
    expect(component.fieldEntries.length).toBe(7);
  });

  it('fieldBadgeClass returns correct class string', () => {
    expect(component.fieldBadgeClass('pass')).toBe('badge badge-pass');
    expect(component.fieldBadgeClass('fail')).toBe('badge badge-fail');
    expect(component.fieldBadgeClass('warning')).toBe('badge badge-warning');
    expect(component.fieldBadgeClass('unreadable')).toBe('badge badge-unreadable');
  });

  it('overallBadgeClass returns correct class string', () => {
    expect(component.overallBadgeClass('approved')).toBe('badge badge-approved');
    expect(component.overallBadgeClass('rejected')).toBe('badge badge-rejected');
    expect(component.overallBadgeClass('needs_review')).toBe('badge badge-needs_review');
  });

  it('fieldEntries contain expected keys', () => {
    component.result = mockResult;
    const keys = component.fieldEntries.map((e) => e.key);
    expect(keys).toContain('brand_name');
    expect(keys).toContain('government_warning');
  });
});
