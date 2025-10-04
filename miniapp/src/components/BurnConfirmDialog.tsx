import ConfirmDialog from './ConfirmDialog';

interface BurnConfirmDialogProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  cardName?: string | null;
}

const BurnConfirmDialog = ({
  isOpen,
  onConfirm,
  onCancel,
  cardName
}: BurnConfirmDialogProps) => {
  const promptText = cardName
    ? `Burn ${cardName}?`
    : 'Burn this card?';

  return (
    <ConfirmDialog
      isOpen={isOpen}
      onRequestClose={onCancel}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <p>{promptText}</p>
    </ConfirmDialog>
  );
};

export default BurnConfirmDialog;
