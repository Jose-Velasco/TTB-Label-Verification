import { TestBed, ComponentFixture } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { ApplicationFormComponent } from './application-form.component';

describe('ApplicationFormComponent', () => {
  let fixture: ComponentFixture<ApplicationFormComponent>;
  let component: ApplicationFormComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ApplicationFormComponent, ReactiveFormsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(ApplicationFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('form is invalid when empty fields are cleared', () => {
    component.form.get('brand_name')!.setValue('');
    expect(component.form.invalid).toBe(true);
  });

  it('form is valid when all required fields are filled', () => {
    component.form.patchValue({
      brand_name: "Stone's Throw",
      class_type: 'American Whiskey',
      alcohol_content: '40% ALC/VOL',
      net_contents: '750 mL',
      bottler_info: 'Bottled by Stone\'s Throw Distillery',
      country_of_origin: 'USA',
      // government_warning is pre-filled with CANONICAL_GOVERNMENT_WARNING
    });
    expect(component.form.valid).toBe(true);
  });

  it('emits saved event with form value on valid submit', () => {
    let emitted: unknown;
    component.saved.subscribe((v) => (emitted = v));

    component.form.patchValue({
      brand_name: "Stone's Throw",
      class_type: 'American Whiskey',
      alcohol_content: '40% ALC/VOL',
      net_contents: '750 mL',
      bottler_info: "Bottled by Stone's Throw Distillery",
      country_of_origin: 'USA',
    });

    component.onSubmit();
    expect(emitted).toBeTruthy();
  });

  it('does not emit when form is invalid', () => {
    let emitted = false;
    component.saved.subscribe(() => (emitted = true));

    component.form.get('brand_name')!.setValue('');
    component.onSubmit();

    expect(emitted).toBe(false);
  });
});
