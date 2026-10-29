import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { ThemeContext } from './theme-context'
import { applyTheme, readTheme, type Theme } from './theme'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readTheme)
  useEffect(() => { applyTheme(theme) }, [theme])
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === 'sisacare-theme') setTheme(readTheme())
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])
  const value = useMemo(() => ({ theme, toggleTheme: () => setTheme(current => current === 'light' ? 'dark' : 'light') }), [theme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
