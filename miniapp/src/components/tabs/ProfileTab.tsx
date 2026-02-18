import { useState, useEffect, useRef } from 'react';
import { ProfileView } from '@/components/profile';
import Loading from '@/components/common/Loading';
import { ApiService } from '@/services/api';
import type { UserProfile } from '@/types';

interface ProfileTabProps {
  userId: number;
  chatId: string | null;
  initData: string;
  isActive: boolean;
}

const ProfileTab = ({ userId, chatId, initData, isActive }: ProfileTabProps) => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (fetchedRef.current || !chatId) {
      setLoading(false);
      if (!chatId) setError('Profile is unavailable outside a chat context.');
      return;
    }
    fetchedRef.current = true;

    ApiService.fetchUserProfile(userId, chatId, initData)
      .then((result) => setProfile(result))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load profile'))
      .finally(() => setLoading(false));
  }, [userId, chatId, initData]);

  // Silently re-fetch when the tab becomes active again (keeps balances fresh)
  // Throttled to at most once every 5 seconds
  const lastFetchRef = useRef(0);
  useEffect(() => {
    if (!isActive || !fetchedRef.current || !chatId) return;
    if (Date.now() - lastFetchRef.current < 5_000) return;
    lastFetchRef.current = Date.now();
    ApiService.fetchUserProfile(userId, chatId, initData)
      .then((result) => setProfile(result))
      .catch(() => {/* keep stale data on silent refresh failure */});
  }, [isActive, userId, chatId, initData]);

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
