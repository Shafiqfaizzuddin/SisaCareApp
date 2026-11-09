import { ClipboardList, LogOut } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { ThemeToggle } from '../components/common/ThemeToggle'
import { useRole } from '../features/authentication/useRole'

export function StaffLayout() {
  const { user, signOut } = useRole()
  return <div className="admin-shell staff-shell"><aside className="admin-sidebar staff-sidebar"><Brand compact />
    <nav aria-label="Staff navigation"><NavLink to="/staff"><ClipboardList size={18} />My assigned tasks</NavLink></nav>
    <div className="admin-sidebar__footer"><Link to="/" onClick={() => void signOut()} aria-label="Sign out"><LogOut size={17} />Sign out</Link></div>
  </aside><div className="admin-workspace"><header className="admin-topbar staff-topbar"><div>
    <span className="admin-topbar__label">Collection team</span><strong>{user?.name ?? 'Staff / Driver'}</strong>
  </div><ThemeToggle compact /></header><main className="admin-content staff-content"><Outlet /></main></div></div>
}
