import { useCallback, useEffect, useState } from "react";
import {
  applyServerProfilePrefs,
  loadProfilePrefs,
  PREFS_CHANGED_EVENT,
  saveProfilePrefs,
  syncProfilePrefsToServer,
} from "./profilePrefs.js";

/** Live profile prefs for the signed-in account — local cache + server sync. */
export function useProfilePrefs(email) {
  const [prefs, setPrefsState] = useState(() => loadProfilePrefs(email));

  useEffect(() => {
    setPrefsState(loadProfilePrefs(email));
  }, [email]);

  useEffect(() => {
    function onPrefsChanged(e) {
      if (e.detail?.email === email) {
        setPrefsState(e.detail.prefs);
      }
    }
    window.addEventListener(PREFS_CHANGED_EVENT, onPrefsChanged);
    return () => window.removeEventListener(PREFS_CHANGED_EVENT, onPrefsChanged);
  }, [email]);

  const setPrefs = useCallback(
    (patch) => {
      if (!email) return;
      setPrefsState((prev) => {
        const next = { ...prev, ...patch };
        saveProfilePrefs(email, next);
        syncProfilePrefsToServer(next).catch(() => {});
        return next;
      });
    },
    [email],
  );

  const hydrateFromServer = useCallback(
    (me) => {
      if (!email || !me?.email) return;
      const merged = applyServerProfilePrefs(email, me);
      setPrefsState(merged);
    },
    [email],
  );

  return [prefs, setPrefs, hydrateFromServer];
}
