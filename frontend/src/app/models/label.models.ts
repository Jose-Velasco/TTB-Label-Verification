// TypeScript interfaces mirroring backend/app/models/label.py exactly.
// Field names use snake_case to match the JSON FastAPI serialises by default.

export type FieldStatus = 'pass' | 'fail' | 'warning' | 'unreadable';
export type OverallStatus = 'approved' | 'rejected' | 'needs_review';

export interface ApplicationData {
  brand_name: string;
  class_type: string;
  alcohol_content: string;
  net_contents: string;
  bottler_info: string;
  country_of_origin: string;
  government_warning: string;
}

export interface ExtractedApplicationData {
  brand_name: string | null;
  class_type: string | null;
  alcohol_content: string | null;
  net_contents: string | null;
  bottler_info: string | null;
  country_of_origin: string | null;
  government_warning: string | null;
}

export interface FieldResult {
  status: FieldStatus;
  extracted_value: string | null;
  expected_value: string;
  note: string | null;
}

export interface VerificationResult {
  overall_status: OverallStatus;
  brand_name: FieldResult;
  class_type: FieldResult;
  alcohol_content: FieldResult;
  net_contents: FieldResult;
  bottler_info: FieldResult;
  country_of_origin: FieldResult;
  government_warning: FieldResult;
  processing_time_ms: number | null;
  image_quality_note: string | null;
  filename: string | null;
  skipped: boolean;
}
