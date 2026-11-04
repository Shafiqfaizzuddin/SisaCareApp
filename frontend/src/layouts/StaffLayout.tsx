import { ClipboardList, LogOut } from 'lucide-react'
import { Link, Outlet } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { ThemeToggle } from '../components/common/ThemeToggle'
import { useRole } from '../features/authentication/useRole'

export function StaffLayout() {
  const { user, signOut } = useRole()
  return <div className="admin-shell"><aside className="admin-sidebar"><Brand compact />
    <nav aria-label="Staff navigation"><Link to="/staff"><ClipboardList size={18} />My assigned tasks</Link></nav>
    <div className="admin-sidebar__footer"><Link to="/" onClick={() => void signOut()}><LogOut size={17} />Sign out</Link></div>
  </aside><div className="admin-workspace"><header className="admin-topbar"><div>
    <span className="admin-topbar__label">Collection team</span><strong>{user?.name ?? 'Staff / Driver'}</strong>
  </div><ThemeToggle compact /></header><main className="admin-content"><Outlet /></main></div></div>
}
