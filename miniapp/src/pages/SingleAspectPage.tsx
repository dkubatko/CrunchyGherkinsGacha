import { useEffect } from 'react';
import { SingleAspectView } from '@/components/aspects';
import { useOrientation } from '@/hooks';
import { TelegramUtils } from '@/utils/telegram';
import '@/App.css';

interface SingleAspectPageProps {
  aspectId: number;
  initData: string;
}

export const SingleAspectPage = ({ aspectId, initData }: SingleAspectPageProps) => {
  const { orientation, orientationKey } = useOrientation({ enabled: true });

  useEffect(() => {
    TelegramUtils.expandApp();
    TelegramUtils.hideBackButton();
  }, []);

  return (
    <div className="app-container">
      <SingleAspectView
        aspectId={aspectId}
        initData={initData}
        orientation={orientation}
        orientationKey={orientationKey}
      />
    </div>
  );
};
