import { useState, useEffect } from 'react';
import './LandingPage.css';

// Import card images
import cardCommon from '../assets/landing/card_common.jpeg';
import cardRare from '../assets/landing/card_rare.jpeg';
import cardEpic from '../assets/landing/card_epic.jpeg';
import cardLegendary from '../assets/landing/card_legenedary.jpeg';
import cardUnique from '../assets/landing/card_unique.jpeg';
import logo from '../assets/landing/logo.png';
import gachaIcon from '../assets/gacha.ico';

// Telegram icon SVG component
const TelegramIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor">
    <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
  </svg>
);

// Claim icon SVG component
const ClaimIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"></polyline>
  </svg>
);

// Feature icons
const CollectionIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="9" rx="1"></rect>
    <rect x="14" y="3" width="7" height="5" rx="1"></rect>
    <rect x="14" y="12" width="7" height="9" rx="1"></rect>
    <rect x="3" y="16" width="7" height="5" rx="1"></rect>
  </svg>
);

const TradeIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="17 1 21 5 17 9"></polyline>
    <path d="M3 11V9a4 4 0 0 1 4-4h14"></path>
    <polyline points="7 23 3 19 7 15"></polyline>
    <path d="M21 13v2a4 4 0 0 1-4 4H3"></path>
  </svg>
);

const CasinoIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"></circle>
    <path d="M12 6v2"></path>
    <path d="M12 16v2"></path>
    <path d="M6 12h2"></path>
    <path d="M16 12h2"></path>
    <circle cx="12" cy="12" r="4" fill="currentColor" opacity="0.3"></circle>
    <text x="12" y="14" textAnchor="middle" fontSize="6" fill="currentColor" fontWeight="bold">$</text>
  </svg>
);

const GeminiIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2L14.4 9.6L22 12L14.4 14.4L12 22L9.6 14.4L2 12L9.6 9.6L12 2Z" />
  </svg>
);

// Card data for the preview
const cards = [
  { src: cardCommon, label: 'Common', rarity: 'common' },
  { src: cardRare, label: 'Rare', rarity: 'rare' },
  { src: cardEpic, label: 'Epic', rarity: 'epic' },
  { src: cardLegendary, label: 'Legendary', rarity: 'legendary' },
  { src: cardUnique, label: 'Unique', rarity: 'unique' },
];

// Features data
const features = [
  {
    icon: <GeminiIcon />,
    title: 'AI-Powered Likeness',
    description: 'Powered by Gemini, cards are generated featuring you and your friends in unique styles'
  },
  {
    icon: <CollectionIcon />,
    title: 'Build Your Collection',
    description: 'Collect cards of all rarities from Common to Unique. Complete sets and show off your collection'
  },
  {
    icon: <TradeIcon />,
    title: 'Trade with Friends',
    description: 'Trade duplicate cards with other collectors. Find the cards you need to complete your sets'
  },
  {
    icon: <CasinoIcon />,
    title: 'Play Mini-Games',
    description: <>Try your luck in <strong>Slots</strong>, <strong>Minesweeper</strong>, or <strong>Ride the Bus</strong> to win extra cards and other rewards!</>
  }
];

const BOT_USERNAME = 'CrunchyGherkinsGachaBot';

export const LandingPage = () => {
  const botLink = `https://t.me/${BOT_USERNAME}`;
  const [activeFeature, setActiveFeature] = useState<number | null>(null);
  
  // Demo interaction state
  const [demoState, setDemoState] = useState<'idle' | 'rolling' | 'rolled' | 'claimed'>('idle');
  const [showRollingMessage, setShowRollingMessage] = useState(false);
  const [rolledCard, setRolledCard] = useState(cards[0]);

  // Set page title and favicon
  useEffect(() => {
    document.title = 'Crunchy Gherkins Gacha';
    const link = document.querySelector("link[rel~='icon']") as HTMLLinkElement | null;
    if (link) {
      link.href = gachaIcon;
    } else {
      const newLink = document.createElement('link');
      newLink.rel = 'icon';
      newLink.href = gachaIcon;
      document.head.appendChild(newLink);
    }
  }, []);

  const handleFeatureClick = (index: number) => {
    setActiveFeature(activeFeature === index ? null : index);
  };

  const handleRollClick = () => {
    if (demoState !== 'idle') return;
    // Pick a random card
    const randomCard = cards[Math.floor(Math.random() * cards.length)];
    setRolledCard(randomCard);
    setDemoState('rolling');
    // Stagger the rolling message appearance
    setTimeout(() => {
      setShowRollingMessage(true);
    }, 400);
    setTimeout(() => {
      setDemoState('rolled');
    }, 1900);
  };

  const handleClaimClick = () => {
    if (demoState !== 'rolled') return;
    setDemoState('claimed');
  };

  const resetDemo = () => {
    setDemoState('idle');
    setShowRollingMessage(false);
  };

  return (
    <div className="landing-page">
      <div className="landing-container">
        {/* Hero Section */}
        <section className="landing-hero">
          <img src={logo} alt="Crunchy Gherkins" className="landing-logo" />
          <h1 className="landing-title">Crunchy Gherkins Gacha</h1>
          <p className="landing-subtitle">
            Collect AI-generated cards featuring you & your friends, play mini-games, 
            and build the ultimate collection in Telegram
          </p>
          <a href={botLink} target="_blank" rel="noopener noreferrer" className="landing-cta">
            <TelegramIcon />
            Start Playing
          </a>
        </section>

        {/* Cards Preview Section */}
        <section className="landing-section">
          <h2 className="landing-section-title">Discover Rare Cards</h2>
          <div className="landing-cards-preview">
            {cards.map((card, index) => (
              <div key={index} className="landing-card-wrapper" data-rarity={card.rarity}>
                <div className="landing-card">
                  <img src={card.src} alt={card.label} />
                </div>
                <span className="landing-card-label">{card.label}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Bot Demo Section */}
        <section className="landing-section">
          <h2 className="landing-section-title">How It Works</h2>
          <div className="landing-demo">
            {/* Demo Header */}
            <div className="landing-demo-header">
              <img src={logo} alt="Bot" className="landing-demo-avatar" />
              <div className="landing-demo-bot-info">
                <span className="landing-demo-bot-name">Crunchy Gherkins Gacha Bot</span>
                <span className="landing-demo-bot-status">online</span>
              </div>
            </div>
            
            {/* Demo Messages */}
            <div className="landing-demo-messages">
              {/* Placeholder text - shown only in idle state */}
              {demoState === 'idle' && (
                <div className="landing-demo-placeholder">
                  Press the button below to start...
                </div>
              )}

              {/* User /roll message - appears after clicking roll */}
              {demoState !== 'idle' && (
                <div className="landing-demo-message user fade-in">
                  /roll
                </div>
              )}

              {/* Rolling message - appears staggered after roll */}
              {showRollingMessage && (
                <div className={`landing-demo-message bot fade-in ${demoState === 'rolling' ? 'pulsing' : ''}`}>
                  🎲 Rolling for a card...
                </div>
              )}

              {/* Card response - appears after rolling */}
              {(demoState === 'rolled' || demoState === 'claimed') && (
                <div className="landing-demo-card-response fade-in">
                  <div className="landing-demo-rolled-card" data-rarity={rolledCard.rarity}>
                    <img src={rolledCard.src} alt="Rolled card" />
                  </div>
                  <button 
                    className={`landing-demo-claim-btn ${demoState === 'claimed' ? 'claimed' : ''}`}
                    onClick={handleClaimClick}
                    disabled={demoState === 'claimed'}
                  >
                    <ClaimIcon />
                    {demoState === 'claimed' ? 'Claimed!' : 'Claim Card'}
                  </button>
                </div>
              )}
            </div>

            {/* Input area at bottom */}
            <div className="landing-demo-input">
              {demoState === 'claimed' ? (
                <button 
                  className="landing-demo-roll-btn restart"
                  onClick={resetDemo}
                >
                  ↺ Try Again
                </button>
              ) : (
                <button 
                  className={`landing-demo-roll-btn ${demoState !== 'idle' ? 'sent' : ''}`}
                  onClick={handleRollClick}
                  disabled={demoState !== 'idle'}
                >
                  {demoState === 'idle' ? 'Tap to /roll' : 'Sent!'}
                </button>
              )}
            </div>
          </div>
        </section>

        {/* Features Section */}
        <section className="landing-section">
          <h2 className="landing-section-title">Features</h2>
          <div className="landing-features">
            {features.map((feature, index) => (
              <div 
                key={index} 
                className={`landing-feature ${activeFeature === index ? 'active' : ''}`}
                onClick={() => handleFeatureClick(index)}
              >
                <div className="landing-feature-header">
                  <div className="landing-feature-icon">{feature.icon}</div>
                  <h3 className="landing-feature-title">{feature.title}</h3>
                </div>
                <p className="landing-feature-description">{feature.description}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Footer CTA */}
        <section className="landing-footer">
          <p className="landing-footer-text">Ready to start your collection?</p>
          <a href={botLink} target="_blank" rel="noopener noreferrer" className="landing-cta">
            <TelegramIcon />
            Open in Telegram
          </a>
        </section>
      </div>
    </div>
  );
};
