import React, { useCallback, useEffect, useReducer, useRef } from 'react';
import { AdminApiService } from '../../services/adminApi';
import { useAdminStore } from '../../stores/useAdminStore';
import OtpInput from './OtpInput';
import logoUrl from '../../assets/landing/logo.png';
import './Admin.css';

type Phase = 'credentials' | 'otp';

interface State {
  phase: Phase;
  username: string;
  password: string;
  otp: string;
  remember: boolean;
  error: string;
  loading: boolean;
  /** Wall-clock ms when OTP expires (5 min after delivery). */
  otpExpiresAt: number | null;
  /** Wall-clock ms when the next resend is allowed. */
  resendAllowedAt: number | null;
  /** Forces the OTP error animation to restart on each new failure. */
  errorShakeKey: number;
}

const initial: State = {
  phase: 'credentials',
  username: '',
  password: '',
  otp: '',
  remember: false,
  error: '',
  loading: false,
  otpExpiresAt: null,
  resendAllowedAt: null,
  errorShakeKey: 0,
};

type Action =
  | { type: 'field'; key: keyof State; value: State[keyof State] }
  | { type: 'login-start' }
  | { type: 'login-success' }
  | { type: 'login-failure'; error: string }
  | { type: 'verify-start' }
  | { type: 'verify-failure'; error: string }
  | { type: 'resend-start' }
  | { type: 'resend-success' }
  | { type: 'resend-failure'; error: string }
  | { type: 'back-to-credentials' };

const OTP_TTL_MS = 5 * 60 * 1000;
const RESEND_COOLDOWN_MS = 30 * 1000;

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'field':
      return { ...state, [action.key]: action.value };
    case 'login-start':
      return { ...state, loading: true, error: '' };
    case 'login-success': {
      const now = Date.now();
      return {
        ...state,
        loading: false,
        error: '',
        phase: 'otp',
        otp: '',
        otpExpiresAt: now + OTP_TTL_MS,
        resendAllowedAt: now + RESEND_COOLDOWN_MS,
      };
    }
    case 'login-failure':
      return { ...state, loading: false, error: action.error };
    case 'verify-start':
      return { ...state, loading: true, error: '' };
    case 'verify-failure':
      return {
        ...state,
        loading: false,
        error: action.error,
        otp: '',
        errorShakeKey: state.errorShakeKey + 1,
      };
    case 'resend-start':
      return { ...state, loading: true, error: '' };
    case 'resend-success': {
      const now = Date.now();
      return {
        ...state,
        loading: false,
        otp: '',
        otpExpiresAt: now + OTP_TTL_MS,
        resendAllowedAt: now + RESEND_COOLDOWN_MS,
      };
    }
    case 'resend-failure':
      return { ...state, loading: false, error: action.error };
    case 'back-to-credentials':
      return {
        ...state,
        phase: 'credentials',
        otp: '',
        error: '',
        otpExpiresAt: null,
        resendAllowedAt: null,
      };
    default:
      return state;
  }
}

const formatMmSs = (ms: number) => {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
};

const Spinner: React.FC = () => (
  <svg className="admin-spinner" viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeDasharray="40 60" />
  </svg>
);

const AdminLoginPage: React.FC = () => {
  const { setAuth } = useAdminStore();
  const [state, dispatch] = useReducer(reducer, initial);
  const [now, setNow] = React.useState(() => Date.now());

  // Drive countdown timers with a 1s tick — only when relevant.
  useEffect(() => {
    if (state.phase !== 'otp') return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [state.phase]);

  const otpMsLeft = state.otpExpiresAt ? state.otpExpiresAt - now : 0;
  const resendMsLeft = state.resendAllowedAt ? state.resendAllowedAt - now : 0;
  const otpExpired = state.phase === 'otp' && otpMsLeft <= 0;

  const submitCredentials = useCallback(async () => {
    dispatch({ type: 'login-start' });
    try {
      await AdminApiService.login(state.username.trim(), state.password);
      dispatch({ type: 'login-success' });
    } catch (err) {
      dispatch({
        type: 'login-failure',
        error: err instanceof Error ? err.message : 'Login failed',
      });
    }
  }, [state.username, state.password]);

  const verifyOtp = useCallback(
    async (code: string) => {
      dispatch({ type: 'verify-start' });
      try {
        await AdminApiService.verifyOtp(state.username.trim(), code, state.remember);
        setAuth(state.username.trim());
      } catch (err) {
        dispatch({
          type: 'verify-failure',
          error: err instanceof Error ? err.message : 'Verification failed',
        });
      }
    },
    [state.username, state.remember, setAuth],
  );

  // Track verifyOtp in a ref so the OtpInput onComplete callback identity is stable.
  const verifyRef = useRef(verifyOtp);
  useEffect(() => {
    verifyRef.current = verifyOtp;
  }, [verifyOtp]);

  const handleResend = useCallback(async () => {
    if (resendMsLeft > 0) return;
    dispatch({ type: 'resend-start' });
    try {
      await AdminApiService.login(state.username.trim(), state.password);
      dispatch({ type: 'resend-success' });
    } catch (err) {
      dispatch({
        type: 'resend-failure',
        error: err instanceof Error ? err.message : 'Failed to resend code',
      });
    }
  }, [resendMsLeft, state.username, state.password]);

  return (
    <div className="admin-container">
      <div className="admin-login-wrapper">
        <div className="admin-login-card">
          <div className="admin-login-header">
            <img
              className="admin-login-logo"
              src={logoUrl}
              alt=""
              aria-hidden="true"
              draggable={false}
            />
            <h1 className="admin-login-title">
              {state.phase === 'credentials' ? 'Crunchy Gherkins' : 'Verify your code'}
            </h1>
            <p className="admin-login-sub">
              {state.phase === 'credentials'
                ? 'Admin dashboard'
                : 'We sent a 6-digit code to your Telegram.'}
            </p>
          </div>

          {state.phase === 'credentials' ? (
            <form
              className="admin-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (!state.loading) submitCredentials();
              }}
            >
              <div className="admin-field">
                <label htmlFor="username" className="admin-sr-only">Username</label>
                <input
                  id="username"
                  name="username"
                  type="text"
                  placeholder="Username"
                  value={state.username}
                  onChange={(e) =>
                    dispatch({ type: 'field', key: 'username', value: e.target.value })
                  }
                  autoComplete="username"
                  required
                  disabled={state.loading}
                  autoFocus
                />
              </div>
              <div className="admin-field">
                <label htmlFor="password" className="admin-sr-only">Password</label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  placeholder="Password"
                  value={state.password}
                  onChange={(e) =>
                    dispatch({ type: 'field', key: 'password', value: e.target.value })
                  }
                  autoComplete="current-password"
                  required
                  disabled={state.loading}
                />
              </div>

              <label className="admin-remember">
                <input
                  type="checkbox"
                  checked={state.remember}
                  onChange={(e) =>
                    dispatch({ type: 'field', key: 'remember', value: e.target.checked })
                  }
                  disabled={state.loading}
                />
                <span>Keep me signed in</span>
              </label>

              {state.error && (
                <div className="admin-error-slot" aria-live="polite">
                  <div className="admin-error">{state.error}</div>
                </div>
              )}

              <button
                type="submit"
                className="admin-btn admin-btn-primary admin-btn-with-spinner"
                disabled={state.loading || !state.username || !state.password}
              >
                {state.loading && <Spinner />}
                <span>Sign In</span>
              </button>
            </form>
          ) : (
            <form
              className="admin-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (state.otp.length === 6 && !state.loading) verifyOtp(state.otp);
              }}
            >
              <div className="admin-otp-wrap" key={state.errorShakeKey}>
                <OtpInput
                  value={state.otp}
                  onChange={(v) => dispatch({ type: 'field', key: 'otp', value: v })}
                  onComplete={(code) => {
                    if (!state.loading) verifyRef.current(code);
                  }}
                  disabled={state.loading || otpExpired}
                  error={!!state.error}
                  autoFocus
                />
              </div>

              <div className="admin-otp-meta">
                <span className={`admin-otp-timer${otpExpired ? ' admin-otp-timer-expired' : ''}`}>
                  {otpExpired ? 'Code expired' : `Code expires in ${formatMmSs(otpMsLeft)}`}
                </span>
                <button
                  type="button"
                  className="admin-link-btn"
                  onClick={handleResend}
                  disabled={state.loading || resendMsLeft > 0}
                >
                  {resendMsLeft > 0 ? `Resend (${Math.ceil(resendMsLeft / 1000)}s)` : 'Resend code'}
                </button>
              </div>

              {state.error && (
                <div className="admin-error-slot" aria-live="polite">
                  <div className="admin-error">{state.error}</div>
                </div>
              )}

              <button
                type="submit"
                className="admin-btn admin-btn-primary admin-btn-with-spinner"
                disabled={state.loading || state.otp.length !== 6 || otpExpired}
              >
                {state.loading && <Spinner />}
                <span>Verify</span>
              </button>
              <button
                type="button"
                className="admin-btn admin-btn-secondary"
                onClick={() => dispatch({ type: 'back-to-credentials' })}
                disabled={state.loading}
              >
                Back to login
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminLoginPage;
