import React, { useState } from 'react';
import './Poker.css';

interface PokerProps {
  chatId: string;
  initData: string;
}

const Poker: React.FC<PokerProps> = ({ chatId, initData }) => {
  const [loading, setLoading] = useState(false);
  const [players, setPlayers] = useState([
    { id: 1, name: 'Player 1' },
    { id: 2, name: 'Player 2' },
    { id: 3, name: 'Player 3' },
  ]);
  
  // Prevent unused variable warnings - will be used in future steps
  console.log('Poker initialized with chatId:', chatId, 'initData length:', initData.length);

  // Calculate circular positions for players around the table
  const getPlayerPosition = (index: number, total: number) => {
    const angle = (index * 360) / total - 90; // Start from top
    const radius = 140; // Distance from center of table (250px table / 2 + spacing)
    const angleRad = (angle * Math.PI) / 180;
    const x = radius * Math.cos(angleRad);
    const y = radius * Math.sin(angleRad);
    return { x, y };
  };

  const handleJoin = () => {
    setLoading(true);
    // Simulate joining with a slight delay
    setTimeout(() => {
      const newPlayer = {
        id: players.length + 1,
        name: `Player ${players.length + 1}`,
      };
      setPlayers([...players, newPlayer]);
      setLoading(false);
    }, 300);
  };

  return (
    <div className="poker-container">
      <h1>🃏 Poker</h1>
      
      <div className="poker-game">
        <div className="poker-game-space">
          <div className="poker-table-wrapper">
            <div className="poker-table">
              <div className="community-cards">
                <div className="card-outline"></div>
                <div className="card-outline"></div>
                <div className="card-outline"></div>
                <div className="card-outline"></div>
                <div className="card-outline"></div>
              </div>
            </div>
            
            {/* Dynamic player icons */}
            {players.map((player, index) => {
              const { x, y } = getPlayerPosition(index, players.length);
              return (
                <div
                  key={player.id}
                  className="player-icon"
                  style={{
                    left: '50%',
                    top: '50%',
                    transform: `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`,
                  }}
                  title={player.name}
                />
              );
            })}
          </div>
        </div>
        
        <div className="poker-action-space">
          <button 
            className="poker-join-button"
            disabled={loading}
            onClick={handleJoin}
          >
            {loading ? 'Joining...' : 'Join'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Poker;
