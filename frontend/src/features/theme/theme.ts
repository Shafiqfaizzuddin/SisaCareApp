export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'sisacare-theme'

export function readTheme(): Theme {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  if (meta) meta.content = theme === 'dark' ? '#0b1715' : '#0f2a1e'
  try { window.localStorage.setItem(STORAGE_KEY, theme) } catch { /* Browser storage can be disabled. */ }
}
