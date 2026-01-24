import { useEffect } from 'react';
import './App.css';

// Hooks
import { useAppRouter } from './hooks';

// Pages
import { CasinoPage, SingleCardPage, CollectionPage } from './pages';

// Components
import { Title } from './components/common';

// Build info
import { BUILD_INFO } from './build-info';

function App() {
  // Log build info to console for debugging (only once on mount)
  useEffect(() => {
    console.log('App build info:', BUILD_INFO);
  }, []);

  const { route } = useAppRouter();

  // Loading state
  if (route.type === 'loading') {
    return (
      <div className="app-container">
        <Title title="Loading..." loading fullscreen />
      </div>
    );
  }

  // Error state
  if (route.type === 'error') {
    return (
      <div className="app-container">
        <h1>Error: {route.message}</h1>
      </div>
    );
  }

  // Route to appropriate page
  switch (route.type) {
    case 'casino':
      return (
        <CasinoPage
          currentUserId={route.currentUserId}
          chatId={route.chatId}
          initData={route.initData}
        />
      );

    case 'singleCard':
      return (
        <SingleCardPage
          cardId={route.cardId}
          initData={route.initData}
        />
      );

    case 'collection':
      return (
        <CollectionPage
          currentUserId={route.currentUserId}
          targetUserId={route.targetUserId}
          chatId={route.chatId}
          isOwnCollection={route.isOwnCollection}
          enableTrade={route.enableTrade}
          initData={route.initData}
        />
      );

    default:
      return (
        <div className="app-container">
          <h1>Unknown route</h1>
        </div>
      );
  }
}

export default App;
