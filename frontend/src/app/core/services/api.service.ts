import { HttpClient } from "@angular/common/http";
import { Injectable, inject } from "@angular/core";
import { Observable } from "rxjs";
import { environment } from "../../../environments/environment";
import {
  ApplicationData,
  ExtractedApplicationData,
  VerificationResult,
} from "../../models/label.models";

@Injectable({ providedIn: "root" })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBase;

  login(accessKey: string): Observable<void> {
    return this.http.post<void>(`${this.base}/login`, { password: accessKey });
  }

  logout(): Observable<void> {
    return this.http.post<void>(`${this.base}/logout`, {});
  }

  verify(
    file: File,
    applicationData: ApplicationData,
  ): Observable<VerificationResult> {
    const fd = new FormData();
    fd.append("image", file);
    fd.append("application_data", JSON.stringify(applicationData));
    return this.http.post<VerificationResult>(`${this.base}/verify`, fd);
  }

  extract(file: File): Observable<ExtractedApplicationData> {
    const fd = new FormData();
    fd.append("image", file);
    return this.http.post<ExtractedApplicationData>(`${this.base}/extract`, fd);
  }

  // NDJSON streaming via fetch() + ReadableStream — HttpClient doesn't support
  // line-by-line streaming, so we wrap native fetch in an Observable instead.
  verifyBatch(
    files: File[],
    applicationData: ApplicationData,
  ): Observable<VerificationResult> {
    return new Observable<VerificationResult>((observer) => {
      const fd = new FormData();
      files.forEach((f) => fd.append("images", f));
      fd.append("application_data", JSON.stringify(applicationData));

      const controller = new AbortController();

      fetch(`${this.base}/verify-batch`, {
        method: "POST",
        body: fd,
        credentials: "include",
        signal: controller.signal,
      })
        .then(async (response) => {
          if (!response.ok) {
            const text = await response.text().catch(() => response.statusText);
            observer.error(
              new Error(`Batch request failed: ${response.status} ${text}`),
            );
            return;
          }

          if (!response.body) {
            observer.error(new Error("Response body is null"));
            return;
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";

          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split("\n");
              buffer = lines.pop() ?? "";

              for (const line of lines) {
                const trimmed = line.trim();
                if (trimmed) {
                  try {
                    observer.next(JSON.parse(trimmed) as VerificationResult);
                  } catch {
                    // skip malformed lines
                  }
                }
              }
            }

            // flush any remaining content
            if (buffer.trim()) {
              try {
                observer.next(JSON.parse(buffer.trim()) as VerificationResult);
              } catch {
                // ignore
              }
            }

            observer.complete();
          } catch (err) {
            if ((err as Error).name !== "AbortError") observer.error(err);
          }
        })
        .catch((err) => {
          if (err.name !== "AbortError") observer.error(err);
        });

      return () => controller.abort();
    });
  }
}
