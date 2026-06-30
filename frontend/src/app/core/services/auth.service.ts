import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

// The FastAPI auth cookie is httpOnly — the browser cannot read it from JavaScript.
// We track login state with a sessionStorage flag instead. The flag is set after a
// successful POST /api/login and cleared on logout. The cookie itself handles
// server-side authentication on every subsequent request.
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly SESSION_KEY = 'ttb_authenticated';

  // BehaviorSubject so guards and components can react to auth state changes.
  // In Angular this is the idiomatic alternative to RxJS's or NgRx's store for
  // simple boolean state.
  readonly isLoggedIn$ = new BehaviorSubject<boolean>(this.readSession());

  private readSession(): boolean {
    try {
      return sessionStorage.getItem(this.SESSION_KEY) === 'true';
    } catch {
      return false; // sessionStorage blocked (e.g. private browsing restrictions)
    }
  }

  get isLoggedIn(): boolean {
    return this.isLoggedIn$.value;
  }

  setLoggedIn(value: boolean): void {
    try {
      if (value) {
        sessionStorage.setItem(this.SESSION_KEY, 'true');
      } else {
        sessionStorage.removeItem(this.SESSION_KEY);
      }
    } catch {
      // ignore storage errors
    }
    this.isLoggedIn$.next(value);
  }
}
