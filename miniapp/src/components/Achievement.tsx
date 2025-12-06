import { useState } from 'react';
import './Achievement.css';

interface AchievementProps {
  id: string;
  icon: string;
  name: string;
  description: string;
}

const Achievement = ({ icon, name, description }: AchievementProps) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <div 
        className="achievement-item"
        onClick={() => setIsOpen(true)}
      >
        <img src={icon} alt={name} className="achievement-icon-img" />
      </div>

      {isOpen && (
        <div className="achievement-popup-overlay" onClick={() => setIsOpen(false)}>
          <div className="achievement-popup" onClick={e => e.stopPropagation()}>
            <img src={icon} alt={name} className="achievement-popup-icon-img" />
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
