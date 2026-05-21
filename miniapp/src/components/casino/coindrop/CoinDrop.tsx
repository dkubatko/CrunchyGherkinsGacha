import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ApiService } from '@/services/api';
import { TelegramUtils } from '@/utils/telegram';
import { Title, SpinsBadge } from '@/components/common';
import type { CoinDropConfig } from '@/types';
import PlinkoBoard, { type PlinkoBoardHandle } from './PlinkoBoard';
import './CoinDrop.css';
import '../Casino.css';

interface CoinDropProps {
  userId: number;
  chatId: string;
  initData: string;
  initialSpins?: number;
  onSpinsUpdate?: (count: number) => void;
}

const DEFAULT_CONFIG: CoinDropConfig = {
  peg_rows: 8,
  buckets: [
    { multiplier: 10 },
    { multiplier: 2 },
    { multiplier: 1 },
    { multiplier: 0 },
    { multiplier: 1 },
    { multiplier: 2 },
    { multiplier: 10 },
  ],
};

const CoinDrop: React.FC<CoinDropProps> = ({
  userId,
  chatId,
  initData,
  initialSpins,
  onSpinsUpdate,
}) => {
  const [config, setConfig] = useState<CoinDropConfig | null>(null);
  const [spinsBalance, setSpinsBalance] = useState<number>(initialSpins ?? 0);
  const [errorToast, setErrorToast] = useState<string | null>(null);
  const boardRef = useRef<PlinkoBoardHandle | null>(null);
  const errorTimerRef = useRef<number | null>(null);
  const spinsBalanceRef = useRef<number>(initialSpins ?? 0);

  useEffect(() => {
    spinsBalanceRef.current = spinsBalance;
  }, [spinsBalance]);

  // Fetch config once on mount.
  useEffect(() => {
    let cancelled = false;
    ApiService.getCoinDropConfig(initData)
      .then((cfg) => {
        if (!cancelled) setConfig(cfg);
      })
      .catch((err) => {
        console.error('Failed to load Coin Drop config; using defaults', err);
        if (!cancelled) setConfig(DEFAULT_CONFIG);
      });
    return () => {
      cancelled = true;
    };
  }, [initData]);

  // Sync initialSpins -> local state when parent updates it (e.g., daily bonus).
  useEffect(() => {
    if (typeof initialSpins === 'number') setSpinsBalance(initialSpins);
  }, [initialSpins]);

  const showError = useCallback((msg: string) => {
    setErrorToast(msg);
    if (errorTimerRef.current) window.clearTimeout(errorTimerRef.current);
    errorTimerRef.current = window.setTimeout(() => setErrorToast(null), 1700);
  }, []);

  const adjustSpins = useCallback(
    (delta: number) => {
      setSpinsBalance((prev) => {
        const next = Math.max(0, prev + delta);
        spinsBalanceRef.current = next;
        onSpinsUpdate?.(next);
        return next;
      });
    },
    [onSpinsUpdate],
  );

  const handleDrop = useCallback(async () => {
    if (spinsBalanceRef.current <= 0) {
      showError('Not enough spins');
      TelegramUtils.triggerHapticNotification('error');
      return;
    }
    if (!boardRef.current) return;

    TelegramUtils.triggerHapticImpact('light');

    // Optimistic deduction immediately on press so concurrent taps see updated balance.
    adjustSpins(-1);

    try {
      const result = await ApiService.dropCoin(userId, chatId, initData);
      await boardRef.current.dropCoin(result.bucket_index);

      // Credit payout only when the coin lands.
      if (result.payout > 0) {
        adjustSpins(result.payout);
      }

      if (result.multiplier >= 10) {
        TelegramUtils.triggerHapticNotification('success');
      } else if (result.payout > 0) {
        TelegramUtils.triggerHapticImpact('medium');
      } else {
        TelegramUtils.triggerHapticImpact('light');
      }
    } catch (err: unknown) {
      // Refund the optimistic deduction on failure.
      adjustSpins(1);
      const message = err instanceof Error ? err.message : 'Drop failed';
      showError(message);
      TelegramUtils.triggerHapticNotification('error');
    }
  }, [userId, chatId, initData, adjustSpins, showError]);

  if (!config) {
    return (
      <div className="coindrop-container">
        <Title title="⛳ Coin Drop" rightContent={<SpinsBadge count={spinsBalance} />} />
        <div className="coindrop-board-wrapper">
          <div className="coindrop-loading">Loading…</div>
        </div>
      </div>
    );
  }

  const bucketMultipliers = config.buckets.map((b) => b.multiplier);

  return (
    <div className="coindrop-container">
      <Title title="⛳ Coin Drop" rightContent={<SpinsBadge count={spinsBalance} />} />

      <div className="coindrop-board-wrapper">
        <PlinkoBoard
          ref={boardRef}
          pegRows={config.peg_rows}
          bucketCount={config.buckets.length}
          bucketMultipliers={bucketMultipliers}
        />
        {errorToast && <div className="coindrop-toast">{errorToast}</div>}
      </div>

      <button
        type="button"
        className="spin-button"
        onClick={handleDrop}
        disabled={spinsBalance <= 0}
      >
        DROP
      </button>
    </div>
  );
};

export default CoinDrop;
