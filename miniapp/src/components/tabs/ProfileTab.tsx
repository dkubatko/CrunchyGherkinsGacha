import { useState, useEffect, useRef } from 'react';
import { ProfileView } from '@/components/profile';
import Loading from '@/components/common/Loading';
import { ApiService } from '@/services/api';
import type { UserProfile } from '@/types';

interface ProfileTabProps {
  currentUserId: number;
  targetUserId: number;
  isOwnCollection: boolean;
  chatId: string | null;
  initData: string;
}

const ProfileTab = ({
  currentUserId,
  targetUserId,
  isOwnCollection,
  chatId,
  initData,
}: ProfileTabProps) => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (fetchedRef.current) return;

    if (!chatId) {
      setLoading(false);
      setError('Profile is unavailable outside a chat context.');
      return;
    }

    fetchedRef.current = true;

    const fetchProfile = async () => {
      setLoading(true);
      setError(undefined);
      try {
        const userId = isOwnCollection ? currentUserId : targetUserId;
        const result = await ApiService.fetchUserProfile(userId, chatId, initData);
        setProfile(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load profile');
      } finally {
        setLoading(false);
      }
    };

    void fetchProfile();
  }, [currentUserId, targetUserId, isOwnCollection, chatId, initData]);

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
