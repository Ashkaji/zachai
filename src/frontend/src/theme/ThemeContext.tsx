import { createContext, useContext, useEffect, useMemo, useState } from "react";

type ThemeMode = "light" | "dark";

type ThemeContextValue = {
  mode: ThemeMode;
  toggleMode: () => void;
  setMode: (mode: ThemeMode) => void;
};

const STORAGE_KEY = "zachai-theme-mode";

const ThemeContext = createContext<ThemeContextValue | null>(null);

function safeReadTheme(): ThemeMode {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return "dark";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(() => safeReadTheme());

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    localStorage.setItem(STORAGE_KEY, mode);
  }, [mode]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      setMode,
      toggleMode: () => setMode((prev) => (prev === "dark" ? "light" : "dark")),
    }),
    [mode],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used inside ThemeProvider");
  }
  return context;
}
