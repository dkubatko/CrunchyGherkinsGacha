import React from 'react';
import './ActionPanel.css';

export interface ActionButton {
  id: string;
  text: string;
  onClick: () => void;
  variant?: 'primary' | 'secondary';
}

interface ActionPanelProps {
  buttons: ActionButton[];
  visible: boolean;
}

const ActionPanel: React.FC<ActionPanelProps> = ({ buttons, visible }) => {
  if (!visible || buttons.length === 0) {
    return null;
  }

  return (
    <div className="action-panel">
      <div className="action-panel-content">
        {buttons.map((button) => (
          <button
            key={button.id}
            className={`action-button ${button.variant || 'primary'}`}
            onClick={button.onClick}
          >
            {button.text}
          </button>
        ))}
      </div>
    </div>
  );
};

export default ActionPanel;