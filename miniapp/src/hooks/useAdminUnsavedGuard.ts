import { useEffect, useRef } from 'react';
import { registerNavGuard } from './adminNavGuard';

/**
 * When `dirty` is true, blocks navigation away from the page until the user
 * confirms. Three entry points are covered:
 *
 *   - In-app navigation via `useAdminRouter.navigate()` — checks the guard
 *     synchronously before changing the hash. (Most robust path.)
 *   - Browser back/forward — intercepts `hashchange`, prompts, and reverts
 *     the hash if the user declines.
 *   - Page unload / refresh — native `beforeunload` prompt.
 */
export const useAdminUnsavedGuard = (
  dirty: boolean,
  message = 'You have unsaved changes. Leave anyway?',
) => {
  const lastSafeHashRef = useRef<string>(window.location.hash);

  useEffect(() => {
    // Re-baseline on every dirty transition so we know the "safe" hash
    // we'd revert to if the user declines confirmation.
    lastSafeHashRef.current = window.location.hash;
    if (!dirty) return;

    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = message;
      return message;
    };

    const onHashChange = () => {
      const target = window.location.hash;
      const previous = lastSafeHashRef.current;
      if (target === previous) return;
      // eslint-disable-next-line no-alert
      const proceed = window.confirm(message);
      if (proceed) {
        lastSafeHashRef.current = target;
      } else {
        window.history.replaceState(
          null,
          '',
          `${window.location.pathname}${window.location.search}${previous}`,
        );
        window.dispatchEvent(new HashChangeEvent('hashchange'));
      }
    };

    // Register the synchronous navigation guard used by useAdminRouter.
    const unregister = registerNavGuard(() => {
      // eslint-disable-next-line no-alert
      const proceed = window.confirm(message);
      if (proceed) {
        // Update the safe baseline now so the subsequent hashchange
        // (fired by navigate) isn't re-prompted by `onHashChange`.
        // The actual hash change happens right after navigate() returns.
        // We can't know the target hash yet, so just clear the baseline
        // to "current hash" and let the post-navigate hashchange update it.
        lastSafeHashRef.current = window.location.hash;
      }
      return proceed;
    });

    window.addEventListener('beforeunload', onBeforeUnload);
    window.addEventListener('hashchange', onHashChange);
    return () => {
      unregister();
      window.removeEventListener('beforeunload', onBeforeUnload);
      window.removeEventListener('hashchange', onHashChange);
    };
  }, [dirty, message]);
};
