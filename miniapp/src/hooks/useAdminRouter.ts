import { useCallback, useEffect, useState } from 'react';
import { checkNavGuard } from './adminNavGuard';

/**
 * Hash-based router for the admin dashboard.
 *
 * URL shapes:
 *   #/sets                       → sets list (dashboard)
 *   #/sets/:setId?season=:id     → set detail (season encoded so we can hydrate without a list fetch)
 *   #/types                      → types page
 *   (empty / unknown)            → sets list
 */

export type AdminRoute =
  | { kind: 'sets' }
  | { kind: 'types' }
  | { kind: 'setDetail'; setId: number; seasonId: number };

const parseHash = (hash: string): AdminRoute => {
  // location.hash includes the leading '#'. Strip and split.
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  const [pathPart, queryPart] = raw.split('?');
  const segments = pathPart.split('/').filter(Boolean);
  // segments[0] is the route name.
  if (segments.length === 0 || segments[0] === 'sets') {
    if (segments.length >= 2) {
      const setId = Number(segments[1]);
      const params = new URLSearchParams(queryPart ?? '');
      const seasonId = Number(params.get('season') ?? '');
      if (Number.isFinite(setId) && Number.isFinite(seasonId)) {
        return { kind: 'setDetail', setId, seasonId };
      }
    }
    return { kind: 'sets' };
  }
  if (segments[0] === 'types') return { kind: 'types' };
  return { kind: 'sets' };
};

const routeToHash = (route: AdminRoute): string => {
  switch (route.kind) {
    case 'sets':
      return '#/sets';
    case 'types':
      return '#/types';
    case 'setDetail':
      return `#/sets/${route.setId}?season=${route.seasonId}`;
  }
};

const readCurrent = (): AdminRoute => parseHash(window.location.hash);

export const useAdminRouter = () => {
  const [route, setRoute] = useState<AdminRoute>(() => readCurrent());

  useEffect(() => {
    const onChange = () => setRoute(readCurrent());
    window.addEventListener('hashchange', onChange);
    window.addEventListener('popstate', onChange);
    return () => {
      window.removeEventListener('hashchange', onChange);
      window.removeEventListener('popstate', onChange);
    };
  }, []);

  const navigate = useCallback((next: AdminRoute, opts: { replace?: boolean } = {}) => {
    const hash = routeToHash(next);
    if (hash === window.location.hash) return;
    // Ask the active unsaved-changes guard (if any) before changing hash.
    if (!checkNavGuard()) return;
    if (opts.replace) {
      const url = `${window.location.pathname}${window.location.search}${hash}`;
      window.history.replaceState(null, '', url);
      // replaceState doesn't fire hashchange — sync state manually.
      setRoute(next);
    } else {
      window.location.hash = hash; // fires hashchange → setRoute
    }
  }, []);

  const goBack = useCallback(() => {
    // Browser back is intercepted by the unsaved-guard's hashchange listener.
    window.history.back();
  }, []);

  return { route, navigate, goBack };
};
