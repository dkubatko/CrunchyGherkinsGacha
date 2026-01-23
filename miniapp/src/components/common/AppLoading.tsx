import './AppLoading.css';
import { CasinoHeader } from '@/components/casino';

interface AppLoadingProps {
  title?: string;
  spinsCount?: number;
}

const AppLoading: React.FC<AppLoadingProps> = ({ title, spinsCount }) => (
  <div className="app-loading-backdrop">
    <CasinoHeader title={title || 'Loading...'} spinsCount={spinsCount} />
  </div>
);

export default AppLoading;
