import { useState } from 'react';
import { TelegramUtils } from '@/utils/telegram';
import './DailyBonusPopup.css';

interface DailyBonusPopupProps {
  streak: number;
  spinsToGrant: number;
  onClaim: () => Promise<void>;
  onDismiss: () => void;
}

const MAX_DISPLAY_DOTS = 7;

export default function DailyBonusPopup({
  streak,
  spinsToGrant,
  onClaim,
  onDismiss,
}: DailyBonusPopupProps) {
  const [claiming, setClaiming] = useState(false);

  const handleClaim = async () => {
    setClaiming(true);
    TelegramUtils.triggerHapticNotification('success');
    await onClaim();
  };

  // When streak > 7, slide the window so the current day is the last dot.
  // e.g. streak=10 → dots show days 4,5,6,7,8,9,10 (all filled, last is current)
  const startDay = streak <= MAX_DISPLAY_DOTS ? 1 : streak - MAX_DISPLAY_DOTS + 1;
  const filledCount = Math.min(streak, MAX_DISPLAY_DOTS);

  return (
    <div className="daily-bonus-overlay" onClick={onDismiss}>
      <div className="daily-bonus-popup" onClick={(e) => e.stopPropagation()}>
        <div className="daily-bonus-header">
          <span className="daily-bonus-title">Daily bonus</span>
        </div>

        {/* Connected dots with animated fill line */}
        <div className="daily-bonus-track">
          <div className="daily-bonus-track-line">
            <div
              className="daily-bonus-track-fill"
              style={{
                '--fill-pct': `${((filledCount - 1) / (MAX_DISPLAY_DOTS - 1)) * 100}%`,
              } as React.CSSProperties}
            />
          </div>
          {Array.from({ length: MAX_DISPLAY_DOTS }, (_, i) => {
            const day = startDay + i;
            const isFilled = day <= streak;
            const isCurrent = day === streak;
            return (
              <div
                key={i}
                className={`daily-bonus-dot${isFilled ? ' filled' : ''}${isCurrent ? ' current' : ''}`}
                style={{ '--dot-idx': i } as React.CSSProperties}
              >
                <span className="daily-bonus-dot-label">{day}</span>
              </div>
            );
          })}
        </div>

        <div className="daily-bonus-reward">
          <span className="daily-bonus-coin reward-coin" aria-hidden="true" />
          <span className="daily-bonus-spins">{spinsToGrant}</span>
        </div>

        <button
          className="daily-bonus-claim-btn"
          onClick={handleClaim}
          disabled={claiming}
        >
          <span className="daily-bonus-claim-text">
            Claim
          </span>
          <span className="daily-bonus-claim-shine" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
