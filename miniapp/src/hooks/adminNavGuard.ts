/**
 * Cross-module registry for navigation guards.
 *
 * A component can register a synchronous predicate that gets called from
 * `useAdminRouter.navigate()` (and from a hashchange interceptor for the
 * browser back button). The predicate returns `true` to allow navigation,
 * or `false` to block it. Typical use: a dirty form asks the user via
 * `window.confirm`.
 *
 * Only one guard is active at a time — the most recently registered one
 * wins. Returning a disposer keeps registration/cleanup symmetric.
 */

export type NavGuard = () => boolean;

let activeGuard: NavGuard | null = null;

export const registerNavGuard = (guard: NavGuard): (() => void) => {
  activeGuard = guard;
  return () => {
    if (activeGuard === guard) activeGuard = null;
  };
};

/** Returns true if navigation is allowed; false if a guard blocked it. */
export const checkNavGuard = (): boolean => {
  if (!activeGuard) return true;
  try {
    return activeGuard();
  } catch {
    // Treat guard errors as "allow" so we never hard-trap the user.
    return true;
  }
};
