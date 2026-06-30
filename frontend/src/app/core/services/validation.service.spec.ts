import { TestBed } from '@angular/core/testing';
import { ValidationService, CANONICAL_GOVERNMENT_WARNING } from './validation.service';

describe('ValidationService', () => {
  let service: ValidationService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ValidationService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('returns valid for exact canonical warning', () => {
    const result = service.validateGovernmentWarning(CANONICAL_GOVERNMENT_WARNING);
    expect(result.valid).toBe(true);
    expect(result.message).toBeUndefined();
  });

  it('returns valid when canonical warning has surrounding whitespace', () => {
    const result = service.validateGovernmentWarning(`  ${CANONICAL_GOVERNMENT_WARNING}  `);
    expect(result.valid).toBe(true);
  });

  it('returns invalid when prefix is title case', () => {
    const text = CANONICAL_GOVERNMENT_WARNING.replace(
      'GOVERNMENT WARNING:',
      'Government Warning:',
    );
    const result = service.validateGovernmentWarning(text);
    expect(result.valid).toBe(false);
    expect(result.message).toContain('ALL CAPS');
  });

  it('returns invalid when warning text is wrong but prefix is correct', () => {
    const result = service.validateGovernmentWarning('GOVERNMENT WARNING: wrong text here.');
    expect(result.valid).toBe(false);
    expect(result.message).toContain('canonical');
  });

  it('returns invalid for empty string', () => {
    const result = service.validateGovernmentWarning('');
    expect(result.valid).toBe(false);
  });
});
