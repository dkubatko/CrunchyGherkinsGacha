import { useState, useMemo } from 'react';
import type { UserProfile, CardData } from '../types';
import Achievement from './Achievement';
import achievementIcon from '../assets/icons/achievement.png';
import './ProfileView.css';

interface ProfileViewProps {
  profile: UserProfile | null;
  cards: CardData[];
  loading: boolean;
  error?: string;
}

const ProfileView = ({ profile, cards, loading, error }: ProfileViewProps) => {
  const [showRarityBreakdown, setShowRarityBreakdown] = useState(false);

  const rarityCounts = useMemo(() => {
    const counts = {
      Unique: 0,
      Legendary: 0,
      Epic: 0,
      Rare: 0,
      Common: 0,
    };

    cards.forEach(card => {
      const rarity = card.rarity || 'Common';
      // Capitalize first letter to match keys
      const normalizedRarity = rarity.charAt(0).toUpperCase() + rarity.slice(1).toLowerCase();
      if (normalizedRarity in counts) {
        counts[normalizedRarity as keyof typeof counts]++;
      } else {
        counts.Common++;
      }
    });

    return counts;
  }, [cards]);

  if (loading) {
    return <div className="profile-view loading">Loading profile...</div>;
  }

  if (error) {
    return <div className="profile-view error">Error: {error}</div>;
  }

  if (!profile) {
    return <div className="profile-view empty">No profile data available.</div>;
  }

  return (
    <div className="profile-view">
      <div className="profile-header">
        {profile.profile_imageb64 ? (
          <img 
            src={`data:image/png;base64,${profile.profile_imageb64}`} 
            alt={profile.display_name || profile.username} 
            className="profile-avatar"
          />
        ) : (
          <div className="profile-avatar-placeholder">
            {profile.display_name?.[0] || profile.username[0]}
          </div>
        )}
        <h2 className="profile-name">{profile.display_name || profile.username}</h2>
        {profile.display_name && <div className="profile-username">@{profile.username}</div>}
      </div>
      
      <div className="profile-stats">
        <div 
          className={`stat-item clickable ${showRarityBreakdown ? 'active' : ''}`}
          onClick={() => setShowRarityBreakdown(!showRarityBreakdown)}
        >
          <span className="stat-label">Cards</span>
          <span className="stat-value">{cards.length}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Claims</span>
          <span className="stat-value">{profile.claim_balance}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Spins</span>
          <span className="stat-value">{profile.spin_balance}</span>
        </div>

        {showRarityBreakdown && (
          <div className="rarity-breakdown">
            {['Unique', 'Legendary', 'Epic', 'Rare', 'Common'].map(rarity => (
              <div key={rarity} className={`rarity-item ${rarity.toLowerCase()}`}>
                <span className="rarity-label">{rarity[0]}</span>
                <span className="rarity-count">{rarityCounts[rarity as keyof typeof rarityCounts] || 0}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="achievements-section">
        <h3 className="achievements-title">Achievements</h3>
        <div className="achievements-grid">
          <Achievement 
            id="wip"
            icon={achievementIcon}
            name="WIP"
            description="This feature is WIP, stay tuned!"
          />
        </div>
      </div>
    </div>
  );
};

export default ProfileView;
