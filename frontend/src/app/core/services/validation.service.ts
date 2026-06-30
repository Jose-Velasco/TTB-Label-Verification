import { Injectable } from '@angular/core';

// Mirrors backend/app/services/validation.py and backend/app/constants.py.
// Client-side pre-check gives immediate feedback before the API call.
// The backend always performs the authoritative exact-match.
export const CANONICAL_GOVERNMENT_WARNING =
  'GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink ' +
  'alcoholic beverages during pregnancy because of the risk of birth defects. ' +
  '(2) Consumption of alcoholic beverages impairs your ability to drive a car or ' +
  'operate machinery, and may cause health problems.';

export interface WarningValidationResult {
  valid: boolean;
  message?: string;
}

@Injectable({ providedIn: 'root' })
export class ValidationService {
  validateGovernmentWarning(text: string): WarningValidationResult {
    const normalized = text.trim();

    if (normalized === CANONICAL_GOVERNMENT_WARNING) {
      return { valid: true };
    }

    if (!normalized.startsWith('GOVERNMENT WARNING:')) {
      return {
        valid: false,
        message: "Government warning must begin with 'GOVERNMENT WARNING:' in ALL CAPS.",
      };
    }

    return {
      valid: false,
      message:
        'Government warning text does not exactly match the canonical TTB statement.',
    };
  }
}
