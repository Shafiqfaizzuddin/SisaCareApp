import {
  ClipboardList,
  ExternalLink,
  LayoutDashboard,
  LogOut,
  Settings,
  Recycle,
  BookOpen,
} from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { useRole } from '../features/authentication/useRole'
import { displayInitials } from '../lib/display-initials'
import { ThemeToggle } from '../components/common/ThemeToggle'

export function AdminLayout() {
  const { user, signOut } = useRole()
  const location = useLocation()

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <Brand compact />
        <nav aria-label="Administrator navigation">
          <Link to="/admin" className={location.pathname === '/admin' && location.hash !== '#reports' ? 'active' : undefined}>
            <LayoutDashboard size={18} />
            Overview
          </Link>
          <Link to="/admin#reports" className={location.pathname === '/admin' && location.hash === '#reports' ? 'active' : undefined}>
            <ClipboardList size={18} />
            Reports
          </Link>
          <NavLink to="/admin/recycling-points"><Recycle size={18} />Recycling locations</NavLink>
          <NavLink to="/admin/learn"><BookOpen size={18} />Learn content</NavLink>
          <span className="admin-sidebar__disabled">
            <Settings size={18} />
            Settings
          </span>
        </nav>
        <div className="admin-sidebar__footer">
          <Link to="/" aria-label="Public site" title="Public site">
            <ExternalLink size={17} />
            Public site
          </Link>
          <Link to="/" onClick={signOut} aria-label="Sign out" title="Sign out">
            <LogOut size={17} />
            Sign out
          </Link>
        </div>
      </aside>

      <div className="admin-workspace">
        <header className="admin-topbar">
          <div>
            <span className="admin-topbar__label">Municipal administration</span>
            <strong>Waste reports</strong>
          </div>
          <ThemeToggle compact />
          <div className="admin-profile" aria-label="Signed in administrator">
            <span>{user ? displayInitials(user.name) : 'AD'}</span>
            <div>
              <strong>{user?.name ?? 'Administrator'}</strong>
              <small>{user?.title ?? 'Administrator'}</small>
            </div>
          </div>
        </header>
        <main className="admin-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
