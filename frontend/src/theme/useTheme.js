import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "bv-theme";

function systemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function initialPreference() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") return stored;
  return "system";
}

function resolveTheme(preference) {
  return preference === "system" ? systemTheme() : preference;
}

/** Theme preference (light/dark/system) + resolved theme for rendering. */
export function useTheme() {
  const [preference, setPreferenceState] = useState(initialPreference);
  const [theme, setThemeState] = useState(() => resolveTheme(initialPreference()));

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    setThemeState(resolveTheme(preference));
    if (preference !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setThemeState(media.matches ? "dark" : "light");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  const setTheme = useCallback((next) => {
    localStorage.setItem(STORAGE_KEY, next);
    setPreferenceState(next);
    setThemeState(resolveTheme(next));
  }, []);

  /** Toggle between light and dark (sets an explicit preference, not system). */
  const toggleTheme = useCallback(() => {
    setTheme(theme === "dark" ? "light" : "dark");
  }, [setTheme, theme]);

  return { theme, preference, setTheme, toggleTheme };
}
