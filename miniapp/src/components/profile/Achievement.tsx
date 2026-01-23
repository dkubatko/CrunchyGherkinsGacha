import { useState } from 'react';
import './Achievement.css';

interface AchievementProps {
  id: string;
  icon?: string;
  name: string;
  description: string;
}

const Achievement = ({ icon, name, description }: AchievementProps) => {
  const [isOpen, setIsOpen] = useState(false);

  const renderIcon = (className: string) => {
    if (icon) {
      return <img src={icon} alt={name} className={className} />;
    }
    return <div className={`${className} achievement-icon-placeholder`}>?</div>;
  };

  return (
    <>
      <div 
        className="achievement-item"
        onClick={() => setIsOpen(true)}
      >
        {renderIcon('achievement-icon-img')}
      </div>

      {isOpen && (
        <div className="achievement-popup-overlay" onClick={() => setIsOpen(false)}>
          <div className="achievement-popup" onClick={e => e.stopPropagation()}>
            {renderIcon('achievement-popup-icon-img')}
            <h3 className="achievement-popup-title">{name}</h3>
            <p className="achievement-popup-description">{description}</p>
            <button className="achievement-popup-close" onClick={() => setIsOpen(false)}>Close</button>
          </div>
        </div>
      )}
    </>
  );
};

export default Achievement;
