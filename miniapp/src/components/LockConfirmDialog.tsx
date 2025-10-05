import type { CardData, ClaimBalanceState } from '../types';
import ConfirmDialog from './ConfirmDialog';

interface LockConfirmDialogProps {
  isOpen: boolean;
  locking: boolean;
  card: CardData | null;
  claimState?: ClaimBalanceState;
  onConfirm: () => void;
  onCancel: () => void;
}

const LockConfirmDialog = ({
  isOpen,
  locking,
  card,
  claimState,
  onConfirm,
  onCancel
}: LockConfirmDialogProps) => {
  const confirmLabel = locking ? 'Processing...' : 'Yes';

  const renderBalance = () => {
    if (!claimState) {
      return null;
    }

    if (claimState.loading) {
      return (
        <p className="lock-dialog-balance">
          Balance: <em>Loading...</em>
        </p>
      );
    }

    if (claimState.error) {
      return (
        <p className="lock-dialog-balance">
          Balance unavailable
        </p>
      );
    }

    if (claimState.balance !== null) {
      return (
        <p className="lock-dialog-balance">
          Balance: <strong>{claimState.balance}</strong>
        </p>
      );
    }

    return null;
  };

  return (
    <ConfirmDialog
      isOpen={isOpen}
      onRequestClose={onCancel}
      onConfirm={onConfirm}
      onCancel={onCancel}
      confirmLabel={confirmLabel}
      confirmDisabled={locking}
      cancelDisabled={locking}
      disableClose={locking}
    >
      {!card ? (
        <p>No card selected.</p>
      ) : card.locked ? (
        <>
          <p>
            Unlock <strong>{card.modifier} {card.base_name}</strong>?
          </p>
          <p className="lock-dialog-subtitle">
            Claim point will <strong>not</strong> be refunded.
          </p>
          {renderBalance()}
        </>
      ) : (
        <>
          <p>
            Lock <strong>{card.modifier} {card.base_name}</strong>?
          </p>
          <p className="lock-dialog-subtitle">
            This will consume <strong>1 claim point</strong>
          </p>
          {renderBalance()}
        </>
      )}
    </ConfirmDialog>
  );
};

export default LockConfirmDialog;
