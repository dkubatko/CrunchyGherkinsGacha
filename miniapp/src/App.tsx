import { useEffect } from 'react';
import './App.css';

// Hooks
import { useAppRouter } from './hooks';

// Pages
import { SingleCardPage, LandingPage, HubPage } from './pages';
import { AdminApp } from './pages/admin';

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
    case 'landing':
      return <LandingPage />;

    case 'admin':
      return <AdminApp />;

    case 'hub':
      return (
        <HubPage
          currentUserId={route.currentUserId}
          targetUserId={route.targetUserId}
          chatId={route.chatId}
          isOwnCollection={route.isOwnCollection}
          enableTrade={route.enableTrade}
          initData={route.initData}
          initialTab={route.initialTab}
        />
      );

    case 'singleCard':
      return (
        <SingleCardPage
          cardId={route.cardId}
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
