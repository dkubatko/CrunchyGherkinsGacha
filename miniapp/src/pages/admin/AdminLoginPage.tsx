import React, { useState } from 'react';
import { AdminApiService } from '../../services/adminApi';
import { useAdminStore } from '../../stores/useAdminStore';
import './Admin.css';

const AdminLoginPage: React.FC = () => {
  const { setAuth } = useAdminStore();
  const [step, setStep] = useState<'credentials' | 'otp'>('credentials');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await AdminApiService.login(username, password);
      setStep('otp');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const { token } = await AdminApiService.verifyOtp(username, otp);
      setAuth(token, username);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="admin-container">
      <div className="admin-login-wrapper">
        <div className="admin-login-card">
          <h1 className="admin-login-title">🔐 Admin Login</h1>

          {step === 'credentials' ? (
            <form onSubmit={handleLogin} className="admin-form">
              <div className="admin-field">
                <label htmlFor="username">Username</label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  required
                  disabled={loading}
                />
              </div>
              <div className="admin-field">
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  disabled={loading}
                />
              </div>
              {error && <div className="admin-error">{error}</div>}
              <button
                type="submit"
                className="admin-btn admin-btn-primary"
                disabled={loading}
              >
                {loading ? 'Signing in…' : 'Sign In'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtp} className="admin-form">
              <p className="admin-otp-hint">
                A one-time code has been sent to your Telegram account.
              </p>
              <div className="admin-field">
                <label htmlFor="otp">Verification Code</label>
                <input
                  id="otp"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                  autoComplete="one-time-code"
                  required
                  disabled={loading}
                  autoFocus
                />
              </div>
              {error && <div className="admin-error">{error}</div>}
              <button
                type="submit"
                className="admin-btn admin-btn-primary"
                disabled={loading || otp.length !== 6}
              >
                {loading ? 'Verifying…' : 'Verify'}
              </button>
              <button
                type="button"
                className="admin-btn admin-btn-secondary"
                onClick={() => {
                  setStep('credentials');
                  setOtp('');
                  setError('');
                }}
              >
                Back to Login
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminLoginPage;
