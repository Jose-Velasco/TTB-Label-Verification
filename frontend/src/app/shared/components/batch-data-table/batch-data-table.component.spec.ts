import { TestBed, ComponentFixture } from '@angular/core/testing';
import { BatchDataTableComponent, BatchRow } from './batch-data-table.component';

function makeFile(name: string): File {
  return new File(['x'], name, { type: 'image/png' });
}

// Exercises the same private applyCsv() that onCsvSelected() calls after
// Papa.parse finishes — going through the real File + FileReader + Papa.parse
// pipeline in jsdom is flaky/slow and isn't what this bug is about; the bug
// and fix both live in how parsed CSV rows get reconciled against images.
function importCsvRows(component: BatchDataTableComponent, rows: Record<string, string>[]): void {
  (component as unknown as { applyCsv(rows: Record<string, string>[]): void }).applyCsv(rows);
}

function csvRow(
  filename: string,
  overrides: Partial<Record<string, string>> = {},
): Record<string, string> {
  return {
    filename,
    brand_name: '',
    class_type: '',
    alcohol_content: '',
    net_contents: '',
    bottler_info: '',
    country_of_origin: '',
    government_warning: '',
    ...overrides,
  };
}

describe('BatchDataTableComponent', () => {
  let fixture: ComponentFixture<BatchDataTableComponent>;
  let component: BatchDataTableComponent;
  let latestRows: BatchRow[] = [];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [BatchDataTableComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(BatchDataTableComponent);
    component = fixture.componentInstance;
    latestRows = [];
    component.rowsChange.subscribe((rows) => (latestRows = rows));
    fixture.detectChanges();
  });

  it('matches images uploaded AFTER a CSV import (bug repro + fix)', () => {
    // CSV imported first, while no images have been uploaded yet.
    importCsvRows(component, [
      csvRow('label_001.png', { brand_name: "Stone's Throw", class_type: 'American Whiskey' }),
    ]);

    expect(component.unmatchedCsvFilenames()).toEqual(['label_001.png']);

    // Now the matching image is uploaded.
    component.files = [makeFile('label_001.png')];

    const row = latestRows.find((r) => r.filename === 'label_001.png');
    expect(row).toBeTruthy();
    expect(row!.fields.brand_name).toBe("Stone's Throw");
    expect(row!.fields.class_type).toBe('American Whiskey');
    // Previously this stayed permanently "unmatched" even after the image arrived.
    expect(component.unmatchedCsvFilenames()).toEqual([]);
  });

  it('still matches when images are uploaded BEFORE the CSV (no regression)', () => {
    component.files = [makeFile('label_001.png')];
    importCsvRows(component, [
      csvRow('label_001.png', { brand_name: "Stone's Throw", class_type: 'American Whiskey' }),
    ]);

    const row = latestRows.find((r) => r.filename === 'label_001.png');
    expect(row!.fields.brand_name).toBe("Stone's Throw");
    expect(component.unmatchedCsvFilenames()).toEqual([]);
  });

  it('matches interleaved: CSV, then one image, then another image', () => {
    importCsvRows(component, [
      csvRow('label_001.png', { brand_name: 'Brand A' }),
      csvRow('label_002.png', { brand_name: 'Brand B' }),
    ]);
    expect(component.unmatchedCsvFilenames().sort()).toEqual(['label_001.png', 'label_002.png']);

    component.files = [makeFile('label_001.png')];
    expect(component.unmatchedCsvFilenames()).toEqual(['label_002.png']);
    expect(latestRows.find((r) => r.filename === 'label_001.png')!.fields.brand_name).toBe('Brand A');

    component.files = [makeFile('label_001.png'), makeFile('label_002.png')];
    expect(component.unmatchedCsvFilenames()).toEqual([]);
    expect(latestRows.find((r) => r.filename === 'label_002.png')!.fields.brand_name).toBe('Brand B');
  });

  it('does not clobber a manual edit when an unrelated image is added afterward', () => {
    component.files = [makeFile('label_001.png')];
    importCsvRows(component, [csvRow('label_001.png', { brand_name: "Stone's Throw" })]);

    const row = latestRows.find((r) => r.filename === 'label_001.png')!;
    component.onFieldEdit(row, 'brand_name', 'Manually Edited Brand');

    // Adding a second, unrelated file triggers another reconcile() pass.
    component.files = [makeFile('label_001.png'), makeFile('label_002.png')];

    expect(latestRows.find((r) => r.filename === 'label_001.png')!.fields.brand_name).toBe(
      'Manually Edited Brand',
    );
  });

  it('flags duplicate CSV rows for the same filename, keeping the first', () => {
    component.files = [makeFile('label_001.png')];
    importCsvRows(component, [
      csvRow('label_001.png', { brand_name: 'First Brand' }),
      csvRow('label_001.png', { brand_name: 'Second Brand' }),
    ]);

    expect(latestRows.find((r) => r.filename === 'label_001.png')!.fields.brand_name).toBe(
      'First Brand',
    );
    expect(component.unmatchedCsvFilenames()).toEqual(['label_001.png (duplicate row)']);
  });

  it('re-matches everything on a fresh CSV import, overwriting prior values', () => {
    component.files = [makeFile('label_001.png')];
    importCsvRows(component, [csvRow('label_001.png', { brand_name: 'Old Brand' })]);
    expect(latestRows.find((r) => r.filename === 'label_001.png')!.fields.brand_name).toBe(
      'Old Brand',
    );

    importCsvRows(component, [csvRow('label_001.png', { brand_name: 'New Brand' })]);
    expect(latestRows.find((r) => r.filename === 'label_001.png')!.fields.brand_name).toBe(
      'New Brand',
    );
  });

  it('renders Status as the first column, and highlights incomplete rows', () => {
    component.files = [makeFile('label_001.png'), makeFile('label_002.png')];
    importCsvRows(component, [
      csvRow('label_001.png', {
        brand_name: 'Brand A',
        class_type: 'Bourbon',
        alcohol_content: '40%',
        net_contents: '750 mL',
        bottler_info: 'Some Co',
        country_of_origin: 'USA',
        government_warning: 'GOVERNMENT WARNING',
      }),
      // label_002.png left without CSV data -> stays incomplete (blank fields).
    ]);
    fixture.detectChanges();

    const headers = Array.from(fixture.nativeElement.querySelectorAll('th')).map(
      (el: any) => el.textContent.trim(),
    );
    expect(headers[0]).toBe('Status');
    expect(headers[1]).toBe('Filename');

    const rows = Array.from(fixture.nativeElement.querySelectorAll('tbody tr'));
    const completeRow = rows.find((r: any) => r.textContent.includes('label_001.png')) as HTMLElement;
    const incompleteRow = rows.find((r: any) => r.textContent.includes('label_002.png')) as HTMLElement;

    expect(completeRow.classList.contains('row-incomplete')).toBe(false);
    expect(incompleteRow.classList.contains('row-incomplete')).toBe(true);
  });
});
