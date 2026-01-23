import type { ReactNode, MouseEvent } from 'react';

interface ConfirmDialogProps {
  isOpen: boolean;
  onRequestClose: () => void;
  onConfirm: () => void;
  onCancel: () => void;
  confirmLabel?: ReactNode;
  cancelLabel?: ReactNode;
  confirmDisabled?: boolean;
  cancelDisabled?: boolean;
  disableClose?: boolean;
  children: ReactNode;
}

const ConfirmDialog = ({
  isOpen,
  onRequestClose,
  onConfirm,
  onCancel,
  confirmLabel = 'Yes',
  cancelLabel = 'No',
  confirmDisabled = false,
  cancelDisabled = false,
  disableClose = false,
  children
}: ConfirmDialogProps) => {
  if (!isOpen) {
    return null;
  }

  const handleOverlayClick = (event: MouseEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (!disableClose) {
      onRequestClose();
    }
  };

  const handleContentClick = (event: MouseEvent<HTMLDivElement>) => {
    event.stopPropagation();
  };

  return (
    <div
      className="share-dialog-overlay"
      onClick={handleOverlayClick}
      role="presentation"
    >
      <div
        className="share-dialog"
        onClick={handleContentClick}
        role="dialog"
        aria-modal="true"
      >
        {children}
        <div className="share-dialog-buttons">
          <button
            onClick={onConfirm}
            className="share-confirm-btn"
            disabled={confirmDisabled}
          >
            {confirmLabel}
          </button>
          <button
            onClick={onCancel}
            className="share-cancel-btn"
            disabled={cancelDisabled}
          >
            {cancelLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;
