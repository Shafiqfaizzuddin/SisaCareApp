import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../../features/theme/useTheme'

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggleTheme } = useTheme()
  const next = theme === 'light' ? 'dark' : 'light'
  const Icon = theme === 'light' ? Moon : Sun
  return <button type="button" className={`theme-toggle${compact ? ' theme-toggle--compact' : ''}`}
    onClick={toggleTheme} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
    <Icon size={18} aria-hidden="true" />
    {!compact && <span>{theme === 'light' ? 'Dark mode' : 'Light mode'}</span>}
  </button>
}
