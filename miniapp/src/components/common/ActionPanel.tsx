import React from 'react';
import { createPortal } from 'react-dom';
import './ActionPanel.css';

export interface ActionButton {
  id: string;
  text: string;
  onClick: () => void;
  variant?: 'primary' | 'secondary' | 'burn-red' | 'lock-grey';
  disabled?: boolean;
}

interface ActionPanelProps {
  buttons: ActionButton[];
  visible: boolean;
}

const ActionPanel: React.FC<ActionPanelProps> = ({ buttons, visible }) => {
  if (!visible || buttons.length === 0) {
    return null;
  }

  return createPortal(
    <div className="action-panel">
      <div className="action-panel-content">
        {buttons.map((button) => (
          <button
            key={button.id}
            className={`action-button ${button.variant || 'primary'}`}
            onClick={button.onClick}
            disabled={button.disabled}
          >
            {button.text}
          </button>
        ))}
      </div>
    </div>,
    document.body
  );
};

export default ActionPanel;