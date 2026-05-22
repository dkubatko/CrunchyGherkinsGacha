import React, { useCallback, useEffect, useRef } from 'react';

interface OtpInputProps {
  length?: number;
  value: string;
  onChange: (value: string) => void;
  onComplete?: (value: string) => void;
  disabled?: boolean;
  error?: boolean;
  autoFocus?: boolean;
}

/**
 * Segmented numeric OTP input. Each cell holds one digit. Supports
 * auto-advance, backspace-to-previous, arrow-key navigation, and
 * paste-to-fill. Calls onComplete once when the full code is entered.
 */
const OtpInput: React.FC<OtpInputProps> = ({
  length = 6,
  value,
  onChange,
  onComplete,
  disabled,
  error,
  autoFocus,
}) => {
  const refs = useRef<Array<HTMLInputElement | null>>([]);
  const lastReportedRef = useRef<string>('');

  // Auto-focus the first empty cell on mount.
  useEffect(() => {
    if (!autoFocus) return;
    const firstEmpty = Math.min(value.length, length - 1);
    refs.current[firstEmpty]?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fire onComplete exactly once when the code transitions to complete.
  useEffect(() => {
    if (value.length === length && lastReportedRef.current !== value) {
      lastReportedRef.current = value;
      onComplete?.(value);
    } else if (value.length < length) {
      lastReportedRef.current = '';
    }
  }, [value, length, onComplete]);

  const focusCell = useCallback((idx: number) => {
    const target = Math.max(0, Math.min(length - 1, idx));
    refs.current[target]?.focus();
    refs.current[target]?.select();
  }, [length]);

  const setDigit = useCallback(
    (idx: number, digit: string) => {
      const cleaned = digit.replace(/\D/g, '').slice(-1);
      const arr = value.padEnd(length, ' ').slice(0, length).split('');
      arr[idx] = cleaned || ' ';
      const next = arr.join('').replace(/ /g, '');
      onChange(next.slice(0, length));
    },
    [length, onChange, value],
  );

  const handleChange = (idx: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    // If the user pasted multi-digit content into one cell, treat as bulk paste.
    const digits = raw.replace(/\D/g, '');
    if (digits.length > 1) {
      const fill = digits.slice(0, length - idx);
      const merged = (value.slice(0, idx) + fill).slice(0, length);
      onChange(merged);
      const nextFocus = Math.min(idx + fill.length, length - 1);
      requestAnimationFrame(() => focusCell(nextFocus));
      return;
    }
    setDigit(idx, digits);
    if (digits) {
      requestAnimationFrame(() => focusCell(idx + 1));
    }
  };

  const handleKeyDown = (idx: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      if (value[idx]) {
        setDigit(idx, '');
      } else if (idx > 0) {
        e.preventDefault();
        setDigit(idx - 1, '');
        focusCell(idx - 1);
      }
      return;
    }
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      focusCell(idx - 1);
      return;
    }
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      focusCell(idx + 1);
      return;
    }
    if (e.key === 'Home') {
      e.preventDefault();
      focusCell(0);
      return;
    }
    if (e.key === 'End') {
      e.preventDefault();
      focusCell(length - 1);
    }
  };

  const handlePaste = (idx: number, e: React.ClipboardEvent<HTMLInputElement>) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '');
    if (!pasted) return;
    e.preventDefault();
    const fill = pasted.slice(0, length - idx);
    const merged = (value.slice(0, idx) + fill).slice(0, length);
    onChange(merged);
    const nextFocus = Math.min(idx + fill.length, length - 1);
    requestAnimationFrame(() => focusCell(nextFocus));
  };

  const cells = Array.from({ length }, (_, i) => i);

  return (
    <div
      className={`admin-otp-grid${error ? ' admin-otp-error' : ''}`}
      role="group"
      aria-label="Verification code"
    >
      {cells.map((i) => (
        <input
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="text"
          inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          pattern="[0-9]*"
          maxLength={length}
          value={value[i] || ''}
          onChange={(e) => handleChange(i, e)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={(e) => handlePaste(i, e)}
          onFocus={(e) => e.target.select()}
          disabled={disabled}
          aria-label={`Digit ${i + 1} of ${length}`}
          className={`admin-otp-cell${value[i] ? ' admin-otp-cell-filled' : ''}`}
        />
      ))}
    </div>
  );
};

export default OtpInput;
