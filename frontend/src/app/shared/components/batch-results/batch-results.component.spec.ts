import { TestBed, ComponentFixture } from '@angular/core/testing';
import { BatchResultsComponent, BatchProgressItem } from './batch-results.component';
import { VerificationResult } from '../../../models/label.models';

function makeResult(overrides: Partial<VerificationResult> = {}): VerificationResult {
  const passField = { status: 'pass' as const, extracted_value: 'x', expected_value: 'x', note: null };
  return {
    overall_status: 'approved',
    brand_name: passField,
    class_type: passField,
    alcohol_content: passField,
    net_contents: passField,
    bottler_info: passField,
    country_of_origin: passField,
    government_warning: passField,
    processing_time_ms: null,
    image_quality_note: null,
    filename: null,
    skipped: false,
    ...overrides,
  };
}

describe('BatchResultsComponent', () => {
  let fixture: ComponentFixture<BatchResultsComponent>;
  let component: BatchResultsComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [BatchResultsComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(BatchResultsComponent);
    component = fixture.componentInstance;
  });

  it('has no average while every item is still pending', () => {
    component.items = [
      { filename: 'a.png', status: 'pending' },
      { filename: 'b.png', status: 'pending' },
    ];
    fixture.detectChanges();

    expect(component.avgProcessingTimeSec).toBeNull();
  });

  // Simulates results streaming in one at a time (as the real batch endpoint
  // does), each with its own processing_time_ms, and checks the running
  // average recomputes live after every arrival rather than only once at the end.
  it('updates the running average live as staggered results stream in', () => {
    const items: BatchProgressItem[] = [
      { filename: 'a.png', status: 'pending' },
      { filename: 'b.png', status: 'pending' },
      { filename: 'c.png', status: 'pending' },
    ];
    component.items = items;
    fixture.detectChanges();
    expect(component.avgProcessingTimeSec).toBeNull();

    // First result arrives: 4000ms -> 4.0s avg.
    component.items = [
      { filename: 'a.png', status: 'done', result: makeResult({ processing_time_ms: 4000 }) },
      items[1],
      items[2],
    ];
    fixture.detectChanges();
    expect(component.avgProcessingTimeSec).toBe('4.0');

    // Second result arrives: 6000ms -> (4000+6000)/2 = 5.0s avg.
    component.items = [
      component.items[0],
      { filename: 'b.png', status: 'done', result: makeResult({ processing_time_ms: 6000 }) },
      items[2],
    ];
    fixture.detectChanges();
    expect(component.avgProcessingTimeSec).toBe('5.0');

    // Third result arrives: 8000ms -> (4000+6000+8000)/3 = 6000ms = 6.0s avg.
    component.items = [
      component.items[0],
      component.items[1],
      { filename: 'c.png', status: 'done', result: makeResult({ processing_time_ms: 8000 }) },
    ];
    fixture.detectChanges();
    expect(component.avgProcessingTimeSec).toBe('6.0');
  });

  it('ignores errored items (no processing_time_ms) when averaging', () => {
    component.items = [
      { filename: 'a.png', status: 'done', result: makeResult({ processing_time_ms: 5000 }) },
      { filename: 'b.png', status: 'error', error: 'boom' },
    ];
    fixture.detectChanges();

    expect(component.avgProcessingTimeSec).toBe('5.0');
  });

  it('renders the formatted average in the summary header', () => {
    component.items = [
      { filename: 'a.png', status: 'done', result: makeResult({ processing_time_ms: 5800 }) },
    ];
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('avg 5.8s/label');
  });
});
