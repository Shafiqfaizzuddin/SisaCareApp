import {
  ArrowRight,
  Award,
  BadgeCheck,
  CheckCircle2,
  ClipboardList,
  Coins,
  Crown,
  LockKeyhole,
  Sparkles,
  Trophy,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ReportStatus } from '../components/reports/ReportStatus'
import { getMemberRewardData } from '../features/authentication/reward-api'
import { useRole } from '../features/authentication/useRole'
import { formatReportDate, getMyReports } from '../features/reporting/report-api'

export function MemberDashboardPage() {
  const { user } = useRole()
  const reportsQuery = useQuery({
    queryKey: ['member-reports', user?.id],
    queryFn: getMyReports,
    enabled: Boolean(user),
  })
  const rewardsQuery = useQuery({
    queryKey: ['member-rewards', user?.id],
    queryFn: () => getMemberRewardData(user?.id ?? ''),
    enabled: Boolean(user),
  })

  if (!user) return null

  const memberReports = reportsQuery.data ?? []
  const rewards = rewardsQuery.data
  const titles = rewards?.titles ?? []
  const achievements = rewards?.achievements ?? []
  const nextTitle = titles.find((title) => title.minimumPoints > user.points)
  const previousThreshold =
    [...titles].reverse().find((title) => title.minimumPoints <= user.points)
      ?.minimumPoints ?? 0
  const progress = nextTitle
    ? ((user.points - previousThreshold) /
        (nextTitle.minimumPoints - previousThreshold)) * 100
    : 100

  return (
    <section className="section member-page">
      <div className="container">
        <header className="member-hero">
          <div className="member-hero__identity">
            <span className="member-hero__avatar">{user.name.split(' ').map((part) => part[0]).join('')}</span>
            <div><p className="eyebrow">Registered member</p><h1>{user.name}</h1><span className="member-title"><Award size={15} /> {user.title}</span></div>
          </div>
          <Link className="button button--primary" to="/report">Submit a new report <ArrowRight size={17} /></Link>
        </header>

        <section className="member-stats" aria-label="Member reward summary">
          <div><Trophy size={20} /><span>Total points</span><strong>{user.points}</strong></div>
          <div><CheckCircle2 size={20} /><span>Valid reports</span><strong>{user.validReports ?? 0}</strong></div>
          <div><Crown size={20} /><span>Points rank</span><strong>{rewards?.pointsRank ? `#${rewards.pointsRank}` : 'New'}</strong></div>
        </section>

        {nextTitle && (
          <section className="progress-panel">
            <div className="progress-panel__heading">
              <span><Sparkles size={20} /></span>
              <div><p>Next title</p><h2>{nextTitle.name}</h2></div>
              <strong>{user.points} / {nextTitle.minimumPoints} pts</strong>
            </div>
            <div className="progress-track" role="progressbar" aria-valuemin={previousThreshold} aria-valuemax={nextTitle.minimumPoints} aria-valuenow={user.points}>
              <span style={{ width: `${Math.min(Math.max(progress, 0), 100)}%` }} />
            </div>
            <p>{nextTitle.description}</p>
          </section>
        )}

        <div className="member-section-heading">
          <div><p className="eyebrow">Milestones</p><h2>Achievements and titles</h2></div>
          <p>Valid reports unlock achievement badges and community titles.</p>
        </div>

        {rewardsQuery.isLoading ? (
          <p className="empty-state">Loading achievements...</p>
        ) : rewardsQuery.isError ? (
          <p className="form-error">Reward progress could not be loaded.</p>
        ) : (
          <section className="achievement-grid">
            {achievements.map((achievement) => (
              <article className={`achievement-card ${achievement.unlocked ? 'achievement-card--unlocked' : ''}`} key={achievement.id}>
                <span className="achievement-card__icon">{achievement.unlocked ? <BadgeCheck size={23} /> : <LockKeyhole size={21} />}</span>
                <div>
                  <span>
                    {achievement.criteriaValue} {achievement.criteriaType === 'valid_reports' ? 'valid reports' : 'points'}
                  </span>
                  <h3>{achievement.name}</h3>
                  <p>{achievement.description}</p>
                </div>
                <strong>{achievement.title}</strong>
              </article>
            ))}
          </section>
        )}

        <div className="member-dashboard-grid">
          <section className="member-panel">
            <header><div><h2>Your recent reports</h2><p>Validation determines the final reward.</p></div><ClipboardList size={20} /></header>
            <div className="member-report-list">
              {reportsQuery.isLoading ? (
                <p className="member-report-list__empty">Loading reports...</p>
              ) : memberReports.length > 0 ? (
                memberReports.map((report) => (
                  <div key={report.id}>
                    <div><strong>{report.reference}</strong><span>{report.location} | {formatReportDate(report.submittedAt)}</span></div>
                    <ReportStatus status={report.status} />
                  </div>
                ))
              ) : (
                <p className="member-report-list__empty">Your submitted reports will appear here.</p>
              )}
            </div>
          </section>

          <section className="member-panel leaderboard-preview">
            <header><div><h2>Recent rewards</h2><p>An auditable history of earned points.</p></div><Coins size={20} /></header>
            <div className="reward-transaction-list">
              {(rewards?.transactions ?? []).slice(0, 5).map((transaction) => (
                <div key={transaction.id}>
                  <span><strong>+{transaction.points}</strong> pts</span>
                  <div><strong>{transaction.description}</strong><p>{formatReportDate(transaction.awardedAt)}</p></div>
                </div>
              ))}
              {rewards && rewards.transactions.length === 0 && <p className="member-report-list__empty">Your first eligible report will start your reward history.</p>}
            </div>
            <Link to="/leaderboard">View community leaderboard <ArrowRight size={16} /></Link>
          </section>
        </div>
      </div>
    </section>
  )
}
