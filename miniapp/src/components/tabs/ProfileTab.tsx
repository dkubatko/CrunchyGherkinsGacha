import { useEffect, useRef } from 'react';
import { ProfileView } from '@/components/profile';
import Loading from '@/components/common/Loading';
import type { UserProfile } from '@/types';

interface ProfileTabProps {
  profile: UserProfile | null;
  loading: boolean;
  error?: string;
  isActive: boolean;
  onRefresh: () => Promise<void>;
}

const ProfileTab = ({ profile, loading, error, isActive, onRefresh }: ProfileTabProps) => {
  // Silently re-fetch when the tab becomes active again (keeps balances fresh)
  // Throttled to at most once every 5 seconds
  const lastFetchRef = useRef(0);
  useEffect(() => {
    if (!isActive || !profile) return;
    if (Date.now() - lastFetchRef.current < 5_000) return;
    lastFetchRef.current = Date.now();
    void onRefresh();
  }, [isActive, profile, onRefresh]);

  if (loading) {
    return <Loading message="Loading profile..." />;
  }

  return (
    <ProfileView
      profile={profile}
      loading={false}
      error={error}
    />
  );
};

export default ProfileTab;
