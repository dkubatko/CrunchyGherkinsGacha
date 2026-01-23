import ConfirmDialog from '../common/ConfirmDialog';
import './BurnConfirmDialog.css';

interface BurnConfirmDialogProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  cardName?: string | null;
  spinReward?: number | null;
  processing?: boolean;
}

const BurnConfirmDialog = ({
  isOpen,
  onConfirm,
  onCancel,
  cardName,
  spinReward,
  processing = false
}: BurnConfirmDialogProps) => {
  const promptContent = cardName && spinReward !== null && spinReward !== undefined
    ? (
      <>
        Burn <strong>{cardName}</strong> for <strong>{spinReward}</strong> spins?
      </>
    )
    : cardName
    ? `Burn ${cardName}?`
    : 'Burn this card?';

  return (
    <ConfirmDialog
      isOpen={isOpen}
      onRequestClose={onCancel}
      onConfirm={onConfirm}
      onCancel={onCancel}
      confirmLabel={processing ? 'Processing...' : 'Yes'}
      confirmDisabled={processing}
      cancelDisabled={processing}
      disableClose={processing}
    >
      <p className="burn-confirm-text">{promptContent}</p>
    </ConfirmDialog>
  );
};

export default BurnConfirmDialog;
