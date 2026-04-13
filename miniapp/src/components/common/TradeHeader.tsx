import { getRarityGradient } from '@/utils/rarityStyles';

interface TradeHeaderProps {
  title: string;
  rarity: string;
}

const TradeHeader: React.FC<TradeHeaderProps> = ({ title, rarity }) => (
  <div className="trade-header">
    <span>Trade for </span>
    <span
      className="trade-header-name"
      style={{
        background: getRarityGradient(rarity),
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        backgroundClip: 'text',
      }}
    >
      {title}
    </span>
  </div>
);

export default TradeHeader;
