"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export const THEME_STORAGE_KEY = "app-theme";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("light");

  // Sync from storage / system preference on mount. The actual `.dark` class is
  // applied pre-paint by the inline script in the root layout (no flash); this
  // just keeps React state in agreement with the DOM.
  useEffect(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY) as Theme | null;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    setThemeState(stored ?? (prefersDark ? "dark" : "light"));
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const value: ThemeContextValue = {
    theme,
    setTheme: setThemeState,
    toggleTheme: () => setThemeState((prev) => (prev === "dark" ? "light" : "dark")),
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
