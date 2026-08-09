import {
  ArrowRight,
  LayoutDashboard,
  LogIn,
  LogOut,
  Menu,
  ShieldCheck,
  Trophy,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { useRole } from '../features/authentication/useRole'

const navigation = [
  { label: 'Home', to: '/' },
  { label: 'Report waste', to: '/report' },
  { label: 'Learn', to: '/education' },
  { label: 'Leaderboard', to: '/leaderboard' },
]

export function PublicLayout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { role, user, signOut } = useRole()

  return (
    <div className="site-shell">
      <header className="public-header">
        <div className="container public-header__inner">
          <Brand />
          <nav
            className={`public-nav ${menuOpen ? 'public-nav--open' : ''}`}
            aria-label="Primary navigation"
          >
            {navigation.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                onClick={() => setMenuOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
            {role === 'user' && user ? (
              <>
                <Link
                  className="member-points"
                  to="/account"
                  onClick={() => setMenuOpen(false)}
                >
                  <Trophy size={16} />
                  {user.points} pts
                </Link>
                <Link
                  className="member-profile-link"
                  to="/account"
                  onClick={() => setMenuOpen(false)}
                >
                  <span>{user.name.split(' ').map((part) => part[0]).join('')}</span>
                  <strong>{user.name}</strong>
                </Link>
                <button
                  className="icon-button public-nav__signout"
                  type="button"
                  aria-label="Sign out"
                  title="Sign out"
                  onClick={() => {
                    void signOut()
                    setMenuOpen(false)
                  }}
                >
                  <LogOut size={17} />
                </button>
              </>
            ) : role === 'admin' ? (
              <>
                <Link
                  className="button button--quiet public-nav__admin"
                  to="/admin"
                  onClick={() => setMenuOpen(false)}
                >
                  <LayoutDashboard size={17} />
                  Admin workspace
                </Link>
                <button
                  className="icon-button public-nav__signout"
                  type="button"
                  aria-label="Sign out"
                  title="Sign out"
                  onClick={() => void signOut()}
                >
                  <LogOut size={17} />
                </button>
              </>
            ) : (
              <>
                <Link
                  className="button button--quiet public-nav__member-login"
                  to="/login"
                  onClick={() => setMenuOpen(false)}
                >
                  <LogIn size={17} />
                  Sign in
                </Link>
                <Link
                  className="icon-button public-nav__admin"
                  to="/admin/login"
                  aria-label="Administrator sign in"
                  title="Administrator sign in"
                  onClick={() => setMenuOpen(false)}
                >
                  <ShieldCheck size={17} />
                </Link>
              </>
            )}
          </nav>
          <button
            className="icon-button public-header__menu"
            type="button"
            aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X size={21} /> : <Menu size={21} />}
          </button>
        </div>
      </header>

      <main>
        <Outlet />
      </main>

      <footer className="public-footer">
        <div className="container public-footer__inner">
          <div>
            <Brand compact />
            <p>Helping communities report illegal dumping clearly and quickly.</p>
          </div>
          <div className="public-footer__links">
            <Link to="/report">
              Make a report <ArrowRight size={15} />
            </Link>
            <Link to="/education">Waste guide</Link>
            <Link to="/leaderboard">Community leaderboard</Link>
            <Link to="/admin/login">Administrator access</Link>
          </div>
          <p className="public-footer__meta">
            Built for cleaner, safer neighbourhoods.
          </p>
        </div>
      </footer>
    </div>
  )
}
