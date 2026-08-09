import {
  BookOpen,
  ClipboardList,
  ExternalLink,
  LayoutDashboard,
  LogOut,
} from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { useRole } from '../features/authentication/useRole'

export function AdminLayout() {
  const { user, signOut } = useRole()

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <Brand compact />
        <nav aria-label="Administrator navigation">
          <NavLink to="/admin" end>
            <LayoutDashboard size={18} />
            Overview
          </NavLink>
          <NavLink to="/admin?view=reports">
            <ClipboardList size={18} />
            Reports
          </NavLink>
          <NavLink to="/admin/education">
            <BookOpen size={18} />
            Education
          </NavLink>
        </nav>
        <div className="admin-sidebar__footer">
          <Link to="/">
            <ExternalLink size={17} />
            Public site
          </Link>
          <Link to="/" onClick={() => void signOut()}>
            <LogOut size={17} />
            Sign out
          </Link>
        </div>
      </aside>

      <div className="admin-workspace">
        <header className="admin-topbar">
          <div>
            <span className="admin-topbar__label">Municipal operations</span>
            <strong>Central district</strong>
          </div>
          <div className="admin-profile" aria-label="Signed in administrator">
            <span>{user?.name.split(' ').map((part) => part[0]).join('') ?? 'AD'}</span>
            <div>
              <strong>{user?.name ?? 'Administrator'}</strong>
              <small>{user?.title ?? 'Municipal Administrator'}</small>
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
