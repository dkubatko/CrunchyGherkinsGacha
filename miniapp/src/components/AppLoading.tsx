import './AppLoading.css';

interface AppLoadingProps {
  title?: string;
}

const AppLoading: React.FC<AppLoadingProps> = ({ title }) => (
  <div className="app-loading-backdrop">
    <span className="app-loading-text">{title || 'Loading...'}</span>
  </div>
);

export default AppLoading;
