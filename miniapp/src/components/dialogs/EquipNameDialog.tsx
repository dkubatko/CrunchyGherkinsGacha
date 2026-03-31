import { useState, useCallback, useEffect } from 'react';
import { ConfirmDialog } from '@/components/common';
import { getRarityGradient } from '@/utils/rarityStyles';
import type { AspectData, CardData } from '@/types';
import './EquipNameDialog.css';

interface EquipNameDialogProps {
  isOpen: boolean;
  aspect: AspectData;
  card: CardData;
  onConfirm: (namePrefix: string) => void;
  onCancel: () => void;
  processing?: boolean;
}

const INVALID_CHARS = new Set(['<', '>', '&', '*', '_', '`']);
const MAX_NAME_LENGTH = 30;

const gradientStyle = (gradient: string) => ({
  background: gradient,
  WebkitBackgroundClip: 'text' as const,
  WebkitTextFillColor: 'transparent' as const,
  backgroundClip: 'text' as const,
});

const EquipNameDialog = ({
  isOpen,
  aspect,
  card,
  onConfirm,
  onCancel,
  processing = false,
}: EquipNameDialogProps) => {
  const defaultName = card.modifier || aspect.display_name || '';
  const [namePrefix, setNamePrefix] = useState(defaultName);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setNamePrefix(card.modifier || aspect.display_name || '');
      setValidationError(null);
    }
  }, [isOpen, card.modifier, aspect.display_name]);

  const validate = useCallback((value: string): string | null => {
    if (value.length === 0) return 'Name is required';
    if (value.length > MAX_NAME_LENGTH) return `Max ${MAX_NAME_LENGTH} characters`;
    for (const ch of value) {
      if (INVALID_CHARS.has(ch)) return 'Contains invalid characters';
    }
    return null;
  }, []);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = e.target.value;
      setNamePrefix(val);
      setValidationError(validate(val));
    },
    [validate],
  );

  const handleConfirm = useCallback(() => {
    const err = validate(namePrefix);
    if (err) {
      setValidationError(err);
      return;
    }
    onConfirm(namePrefix.trim());
  }, [namePrefix, validate, onConfirm]);

  const resultName = namePrefix.trim()
    ? `${namePrefix.trim()} ${card.base_name}`
    : card.base_name;

  const cardDisplayName = [card.modifier, card.base_name].filter(Boolean).join(' ');

  return (
    <ConfirmDialog
      isOpen={isOpen}
      onRequestClose={onCancel}
      onConfirm={handleConfirm}
      onCancel={onCancel}
      confirmLabel={processing ? 'Sending...' : 'Equip'}
      cancelLabel="Cancel"
      confirmDisabled={processing || !!validationError || namePrefix.trim().length === 0}
      cancelDisabled={processing}
      disableClose={processing}
    >
      <div className="equip-name-dialog">
        <p className="equip-name-header">
          Equip{' '}
          <strong style={gradientStyle(getRarityGradient(aspect.rarity))}>
            {aspect.display_name}
          </strong>
          {' '}onto{' '}
          <strong style={gradientStyle(getRarityGradient(card.rarity))}>
            {cardDisplayName}
          </strong>
          ?
        </p>

        <div className="equip-name-field">
          <input
            className={`equip-name-input${validationError ? ' has-error' : ''}`}
            type="text"
            value={namePrefix}
            onChange={handleChange}
            placeholder="Card name"
            maxLength={MAX_NAME_LENGTH}
            disabled={processing}
            autoComplete="off"
          />
          {validationError && (
            <span className="equip-name-error">{validationError}</span>
          )}
        </div>

        <p className="equip-name-result">{resultName}</p>
      </div>
    </ConfirmDialog>
  );
};

export default EquipNameDialog;
