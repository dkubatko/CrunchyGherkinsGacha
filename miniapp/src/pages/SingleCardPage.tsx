import { useEffect } from 'react';
import { SingleCardView } from '@/components/cards';
import { useOrientation } from '@/hooks';
import { TelegramUtils } from '@/utils/telegram';
import '@/App.css';

interface SingleCardPageProps {
  cardId: number;
  initData: string;
}

export const SingleCardPage = ({ cardId, initData }: SingleCardPageProps) => {
  const { orientation, orientationKey } = useOrientation({ enabled: true });

  // Expand app and hide back button on mount
  useEffect(() => {
    TelegramUtils.expandApp();
    TelegramUtils.hideBackButton();
  }, []);

  return (
    <div className="app-container">
      <SingleCardView
        cardId={cardId}
        initData={initData}
        orientation={orientation}
        orientationKey={orientationKey}
      />
    </div>
  );
};
