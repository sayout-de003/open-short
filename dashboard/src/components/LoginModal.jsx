import React, { useEffect, useState } from 'react';
import { Mail, Lock, KeyRound, Check, Loader2, ArrowLeft } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import Modal from './ui/Modal';
import SegmentedControl from './ui/SegmentedControl';

const MODE_OPTIONS = [
  { value: 'login', label: 'Sign in' },
  { value: 'signup', label: 'Sign up' },
  { value: 'magic', label: 'Magic link' },
];

// Sign-in / Sign-up modal:
// - Sign in: email + password -> 6-digit email OTP (except review account)
// - Sign up: email + password -> 6-digit email OTP
// - Magic link & Google OAuth
export default function LoginModal({ onClose, queued = false }) {
  const {
    requestMagicLink,
    loginWithPassword,
    usesPassword,
    signupWithPassword,
    verifySignupOtp,
    loginWithPasswordOtp,
    verifyLoginOtp,
    resendOtp,
    requestPasswordReset,
    confirmPasswordReset,
    loginWithGoogle,
    googleAuthEnabled,
  } = useAuth();

  const [mode, setMode] = useState('login'); // 'login' | 'signup' | 'magic' | 'reset'
  const [step, setStep] = useState('form');  // 'form' | 'otp' | 'sent'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [needsReviewPassword, setNeedsReviewPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (mode !== 'magic' && mode !== 'login') {
      setNeedsReviewPassword(false);
      return undefined;
    }
    const value = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      setNeedsReviewPassword(false);
      return undefined;
    }
    let live = true;
    const t = setTimeout(async () => {
      const yes = await usesPassword(value);
      if (live) setNeedsReviewPassword(yes);
    }, 300);
    return () => { live = false; clearTimeout(t); };
  }, [email, mode, usesPassword]);

  const switchMode = (nextMode) => {
    setMode(nextMode);
    setStep('form');
    setOtp('');
    setPassword('');
    setConfirmPassword('');
    setError('');
    setNotice('');
  };

  const handleFormSubmit = async (e) => {
    e.preventDefault();
    const cleanEmail = email.trim();
    if (!cleanEmail) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (mode === 'login') {
        if (needsReviewPassword) {
          await loginWithPassword(cleanEmail, password);
          onClose();
          return;
        }
        await loginWithPasswordOtp(cleanEmail, password);
        setOtp('');
        setStep('otp');
        return;
      }
      if (mode === 'signup') {
        if (password.length < 8) {
          setError('Password must be at least 8 characters.');
          return;
        }
        if (password !== confirmPassword) {
          setError('Passwords do not match.');
          return;
        }
        await signupWithPassword(cleanEmail, password);
        setOtp('');
        setStep('otp');
        return;
      }
      if (mode === 'reset') {
        await requestPasswordReset(cleanEmail);
        setOtp('');
        setPassword('');
        setStep('otp');
        return;
      }
      const { passwordRequired } = await requestMagicLink(cleanEmail);
      if (passwordRequired) {
        setMode('login');
        setNeedsReviewPassword(true);
      } else {
        setStep('sent');
      }
    } catch (err) {
      setError(err.message || 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  const handleOtpSubmit = async (e) => {
    e.preventDefault();
    const cleanEmail = email.trim();
    const cleanOtp = otp.trim();
    if (cleanOtp.length !== 6) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (mode === 'signup') {
        await verifySignupOtp(cleanEmail, cleanOtp);
        onClose();
      } else if (mode === 'login') {
        await verifyLoginOtp(cleanEmail, cleanOtp);
        onClose();
      } else if (mode === 'reset') {
        if (password.length < 8) {
          setError('New password must be at least 8 characters.');
          return;
        }
        await confirmPasswordReset(cleanEmail, cleanOtp, password);
        onClose();
      }
    } catch (err) {
      setError(err.message || 'Invalid verification code.');
    } finally {
      setBusy(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    setError('');
    setNotice('');
    try {
      await resendOtp(email.trim(), mode);
      setNotice('A new verification code was sent to your email.');
    } catch (err) {
      setError(err.message || 'Could not resend code.');
    } finally {
      setResending(false);
    }
  };

  const title = mode === 'signup'
    ? 'Create your CREOVIS account'
    : mode === 'reset'
      ? 'Reset your password'
      : 'Sign in to CREOVIS';

  return (
    <Modal isOpen onClose={onClose} eyebrow="ACCOUNT" title={title} size="md">
      <p className="text-muted text-sm mb-5 lowercase">
        Access your plan and generate shorts with no API keys.
      </p>

      {queued && (
        <div className="flex items-start gap-2 border border-rule2 rounded-input bg-paper2 px-3 py-2 mb-5">
          <Check size={14} className="mt-0.5 shrink-0 text-ok" />
          <p className="text-xs text-ink2 leading-relaxed m-0">
            Your video is saved. Sign in and the clips start on their own — you will not have to paste it again.
          </p>
        </div>
      )}

      {step !== 'sent' && mode !== 'reset' && step === 'form' && (
        <div className="mb-5">
          <SegmentedControl
            options={MODE_OPTIONS}
            value={mode}
            onChange={switchMode}
            size="sm"
          />
        </div>
      )}

      {step === 'sent' ? (
        <div className="text-center py-6">
          <span className="badge-ok px-3 py-1"><Check size={14} /> sent</span>
          <p className="text-ink font-medium lowercase mt-4">Check your inbox</p>
          <p className="text-muted text-sm mt-1">
            We sent a sign-in link to <b className="text-ink font-medium">{email}</b>. It expires in 15 minutes.
          </p>
        </div>
      ) : step === 'otp' ? (
        <form onSubmit={handleOtpSubmit} className="space-y-3">
          <button
            type="button"
            onClick={() => { setStep('form'); setError(''); setNotice(''); }}
            className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink transition-colors mb-1"
          >
            <ArrowLeft size={14} /> Back
          </button>

          <p className="text-sm text-ink2">
            Enter the 6-digit verification code sent to <b className="text-ink font-medium">{email.trim()}</b>.
          </p>

          <div className="relative">
            <KeyRound size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000"
              className="input-field pl-10 tracking-[0.3em] font-mono"
              autoFocus
            />
          </div>

          {mode === 'reset' && (
            <div className="relative">
              <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="new password (min 8 characters)"
                className="input-field pl-10"
              />
            </div>
          )}

          {notice && <p className="text-ok text-xs">{notice}</p>}
          {error && <p className="text-danger text-sm">{error}</p>}

          <button
            type="submit"
            disabled={busy || otp.trim().length !== 6 || (mode === 'reset' && password.length < 8)}
            className="btn-primary w-full"
          >
            {busy ? (
              <Loader2 size={18} className="animate-spin" />
            ) : mode === 'signup' ? (
              'Verify & create account'
            ) : mode === 'reset' ? (
              'Reset password & sign in'
            ) : (
              'Verify & sign in'
            )}
          </button>

          <div className="flex items-center justify-between pt-1">
            <span className="text-xs text-muted">Code expires in 10 minutes.</span>
            <button
              type="button"
              onClick={handleResend}
              disabled={resending}
              className="text-xs text-ink2 underline underline-offset-2 hover:text-brass transition-colors disabled:opacity-50"
            >
              {resending ? 'Sending…' : 'Resend code'}
            </button>
          </div>
        </form>
      ) : (
        <>
          <form onSubmit={handleFormSubmit} className="space-y-3">
            {mode === 'reset' && (
              <button
                type="button"
                onClick={() => switchMode('login')}
                className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink transition-colors mb-1"
              >
                <ArrowLeft size={14} /> Back to sign in
              </button>
            )}

            <div className="relative">
              <Mail size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@email.com"
                className="input-field pl-10"
                autoFocus
              />
            </div>

            {(mode === 'login' || mode === 'signup') && (
              <div className="relative">
                <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                <input
                  type="password"
                  autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === 'signup' ? 'password (min 8 characters)' : 'password'}
                  className="input-field pl-10"
                />
              </div>
            )}

            {mode === 'signup' && (
              <div className="relative">
                <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                <input
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="confirm password"
                  className="input-field pl-10"
                />
              </div>
            )}

            {mode === 'login' && !needsReviewPassword && (
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => switchMode('reset')}
                  className="text-xs text-muted hover:text-ink transition-colors"
                >
                  Forgot password?
                </button>
              </div>
            )}

            {error && <p className="text-danger text-sm">{error}</p>}

            <button
              type="submit"
              disabled={
                busy ||
                !email.trim() ||
                ((mode === 'login' || mode === 'signup') && !password) ||
                (mode === 'signup' && !confirmPassword)
              }
              className="btn-primary w-full"
            >
              {busy ? (
                <Loader2 size={18} className="animate-spin" />
              ) : mode === 'signup' ? (
                'Continue'
              ) : mode === 'reset' ? (
                'Send reset code'
              ) : mode === 'magic' ? (
                'Email me a sign-in link'
              ) : needsReviewPassword ? (
                'Sign in'
              ) : (
                'Continue'
              )}
            </button>
          </form>

          {googleAuthEnabled && mode !== 'reset' && (
            <>
              <div className="flex items-center gap-3 my-5">
                <div className="flex-1 border-t border-rule" />
                <span className="readout">or</span>
                <div className="flex-1 border-t border-rule" />
              </div>
              <button
                type="button"
                onClick={loginWithGoogle}
                className="btn-ghost w-full"
              >
                <svg width="18" height="18" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
                Continue with Google
              </button>
            </>
          )}

          {/* The account is created by this button, so the terms have to be
              reachable from it: a signup never passes the footer. */}
          <p className="text-muted text-xs mt-5 text-center leading-relaxed">
            By signing in you agree to our{' '}
            <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-ink2 underline underline-offset-2 hover:text-brass transition-colors">Terms of Service</a>
            {' '}and{' '}
            <a href="/privacy" target="_blank" rel="noopener noreferrer" className="text-ink2 underline underline-offset-2 hover:text-brass transition-colors">Privacy Policy</a>.
          </p>
        </>
      )}
    </Modal>
  );
}
