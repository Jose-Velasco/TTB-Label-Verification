import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { authGuard } from './auth.guard';
import { AuthService } from '../services/auth.service';

describe('authGuard', () => {
  const mockAuthService = { isLoggedIn: false };
  const mockRouter = { createUrlTree: jest.fn().mockReturnValue('/login') };

  const runGuard = () =>
    TestBed.runInInjectionContext(() =>
      authGuard({} as never, {} as never),
    );

  beforeEach(() => {
    mockAuthService.isLoggedIn = false;
    mockRouter.createUrlTree.mockClear();

    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: mockAuthService },
        { provide: Router, useValue: mockRouter },
      ],
    });
  });

  it('returns true when logged in', () => {
    mockAuthService.isLoggedIn = true;
    expect(runGuard()).toBe(true);
  });

  it('redirects to /login when not logged in', () => {
    mockAuthService.isLoggedIn = false;
    runGuard();
    expect(mockRouter.createUrlTree).toHaveBeenCalledWith(['/login']);
  });
});
