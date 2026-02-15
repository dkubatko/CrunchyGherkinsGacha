import { ProfileView } from '@/components/profile';
import Loading from '@/components/common/Loading';
import type { UserProfile } from '@/types';

interface ProfileTabProps {
  profile: UserProfile | null;
  loading: boolean;
  error?: string;
}

const ProfileTab = ({ profile, loading, error }: ProfileTabProps) => {
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
