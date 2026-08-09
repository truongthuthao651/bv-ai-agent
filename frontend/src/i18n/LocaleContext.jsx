import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { translate } from "./messages.js";

const STORAGE_KEY = "bv-locale";
const LocaleContext = createContext(null);

export { LocaleContext };

function initialLocale() {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "en" ? "en" : "vi";
}

export function LocaleProvider({ children }) {
  const [locale, setLocaleState] = useState(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale === "en" ? "en" : "vi";
  }, [locale]);

  const setLocale = useCallback((next) => {
    const value = next === "en" ? "en" : "vi";
    localStorage.setItem(STORAGE_KEY, value);
    setLocaleState(value);
  }, []);

  const t = useCallback((key, vars) => translate(locale, key, vars), [locale]);

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within LocaleProvider");
  return ctx;
}
