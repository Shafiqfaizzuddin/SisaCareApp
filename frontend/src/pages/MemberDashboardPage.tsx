import {
  ArrowRight,
  Award,
  BadgeCheck,
  CheckCircle2,
  ClipboardList,
  Crown,
  LockKeyhole,
  Sparkles,
  Trophy,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { ReportStatus } from '../components/reports/ReportStatus'
import { reportSummaries } from '../features/admin-reports/report-data'
import { useRole } from '../features/authentication/useRole'
import { achievements } from '../features/authentication/member-data'

export function MemberDashboardPage() {
  const { user } = useRole()

  if (!user) {
    return null
  }

  const memberReports = reportSummaries.filter(
    (report) => report.reporter === user.name,
  )
  const nextAchievement = achievements.find(
    (achievement) => achievement.pointsRequired > user.points,
  )
  const previousThreshold =
    [...achievements]
      .reverse()
      .find((achievement) => achievement.pointsRequired <= user.points)
      ?.pointsRequired ?? 0
  const progress = nextAchievement
    ? ((user.points - previousThreshold) /
        (nextAchievement.pointsRequired - previousThreshold)) *
      100
    : 100

  return (
    <section className="section member-page">
      <div className="container">
        <header className="member-hero">
          <div className="member-hero__identity">
            <span className="member-hero__avatar">
              {user.name.split(' ').map((part) => part[0]).join('')}
            </span>
            <div>
              <p className="eyebrow">Registered member</p>
              <h1>{user.name}</h1>
              <span className="member-title"><Award size={15} /> {user.title}</span>
            </div>
          </div>
          <Link className="button button--primary" to="/report">
            Submit a new report
            <ArrowRight size={17} />
          </Link>
        </header>

        <section className="member-stats" aria-label="Member reward summary">
          <div>
            <Trophy size={20} />
            <span>Total points</span>
            <strong>{user.points}</strong>
          </div>
          <div>
            <CheckCircle2 size={20} />
            <span>Valid reports</span>
            <strong>{user.validReports}</strong>
          </div>
          <div>
            <Crown size={20} />
            <span>Leaderboard rank</span>
            <strong>{user.rank ? `#${user.rank}` : 'Unranked'}</strong>
          </div>
        </section>

        {nextAchievement && (
          <section className="progress-panel">
            <div className="progress-panel__heading">
              <span><Sparkles size={20} /></span>
              <div>
                <p>Next title</p>
                <h2>{nextAchievement.title}</h2>
              </div>
              <strong>
                {user.points} / {nextAchievement.pointsRequired} pts
              </strong>
            </div>
            <div
              className="progress-track"
              role="progressbar"
              aria-valuemin={previousThreshold}
              aria-valuemax={nextAchievement.pointsRequired}
              aria-valuenow={user.points}
            >
              <span style={{ width: `${Math.min(progress, 100)}%` }} />
            </div>
            <p>{nextAchievement.description}</p>
          </section>
        )}

        <div className="member-section-heading">
          <div>
            <p className="eyebrow">Milestones</p>
            <h2>Achievements and titles</h2>
          </div>
          <p>Valid reports unlock points, achievement badges, and new community titles.</p>
        </div>

        <section className="achievement-grid">
          {achievements.map((achievement) => {
            const unlocked = user.points >= achievement.pointsRequired

            return (
              <article
                className={`achievement-card ${
                  unlocked ? 'achievement-card--unlocked' : ''
                }`}
                key={achievement.id}
              >
                <span className="achievement-card__icon">
                  {unlocked ? <BadgeCheck size={23} /> : <LockKeyhole size={21} />}
                </span>
                <div>
                  <span>{achievement.pointsRequired} points</span>
                  <h3>{achievement.name}</h3>
                  <p>{achievement.description}</p>
                </div>
                <strong>{achievement.title}</strong>
              </article>
            )
          })}
        </section>

        <div className="member-dashboard-grid">
          <section className="member-panel">
            <header>
              <div>
                <h2>Your recent reports</h2>
                <p>Validation determines the final reward.</p>
              </div>
              <ClipboardList size={20} />
            </header>
            <div className="member-report-list">
              {memberReports.map((report) => (
                <div key={report.id}>
                  <div>
                    <strong>{report.reference}</strong>
                    <span>{report.location}</span>
                  </div>
                  <ReportStatus status={report.status} />
                </div>
              ))}
            </div>
          </section>

          <section className="member-panel leaderboard-preview">
            <header>
              <div>
                <h2>Community standing</h2>
                <p>You are currently in the top five.</p>
              </div>
              <Crown size={20} />
            </header>
            <div className="leaderboard-preview__rank">
              <span>{user.rank ? `#${user.rank}` : 'N/A'}</span>
              <div>
                <strong>{user.name}</strong>
                <p>{user.points} points · {user.validReports} valid reports</p>
              </div>
            </div>
            <Link to="/leaderboard">
              View full leaderboard <ArrowRight size={16} />
            </Link>
          </section>
        </div>
      </div>
    </section>
  )
}
