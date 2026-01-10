import React from 'react';
import './CasinoHeader.css';

interface CasinoHeaderProps {
  title: string;
  spinsCount?: number;
}

const CasinoHeader: React.FC<CasinoHeaderProps> = ({ title, spinsCount }) => {
  return (
    <div className="casino-header">
      <h1>{title}</h1>
      {spinsCount !== undefined && (
        <div className="casino-header-spins">
          <span className="casino-header-coin" aria-hidden="true" />
          <span className="casino-header-count">{spinsCount}</span>
        </div>
      )}
    </div>
  );
};

export default CasinoHeader;
