import { Award, Crown, Medal, ShieldCheck, Trophy } from 'lucide-react'
import { useMemo, useState } from 'react'
import { PageIntro } from '../components/common/PageIntro'
import { useRole } from '../features/authentication/useRole'
import {
  demoMember,
  leaderboardEntries,
} from '../features/authentication/member-data'

type LeaderboardMetric = 'points' | 'reports'

export function LeaderboardPage() {
  const [metric, setMetric] = useState<LeaderboardMetric>('points')
  const { role, user } = useRole()
  const rankedEntries = useMemo(
    () =>
      leaderboardEntries
        .map((entry) =>
          entry.id === demoMember.id
            ? {
                ...entry,
                id: role === 'user' && user ? user.id : entry.id,
                name: role === 'user' && user ? user.name : entry.name,
                title: role === 'user' && user ? user.title : entry.title,
                points: role === 'user' && user ? user.points : entry.points,
                validReports:
                  role === 'user' && user
                    ? (user.validReports ?? entry.validReports)
                    : entry.validReports,
                isCurrentUser: role === 'user',
              }
            : entry,
        )
        .sort((a, b) =>
        metric === 'points'
          ? b.points - a.points
          : b.validReports - a.validReports,
      ),
    [metric, role, user],
  )

  return (
    <section className="section leaderboard-page">
      <div className="container">
        <PageIntro
          eyebrow="Community rewards"
          title="SisaCare leaderboard"
          description="Recognising registered members whose valid reports help response teams keep neighbourhoods clean and safe."
          actions={
            <div className="segmented-control" aria-label="Leaderboard ranking method">
              <button
                className={metric === 'points' ? 'active' : ''}
                type="button"
                onClick={() => setMetric('points')}
              >
                <Trophy size={15} /> Points
              </button>
              <button
                className={metric === 'reports' ? 'active' : ''}
                type="button"
                onClick={() => setMetric('reports')}
              >
                <ShieldCheck size={15} /> Valid reports
              </button>
            </div>
          }
        />

        <div className="leaderboard-podium">
          {rankedEntries.slice(0, 3).map((entry, index) => (
            <article
              className={`podium-card podium-card--${index + 1}`}
              key={entry.id}
            >
              <span className="podium-card__rank">
                {index === 0 ? <Crown size={21} /> : <Medal size={20} />}
              </span>
              <div className="podium-card__avatar">
                {entry.name.split(' ').map((part) => part[0]).join('')}
              </div>
              <span>#{index + 1}</span>
              <h2>{entry.name}</h2>
              <p><Award size={14} /> {entry.title}</p>
              <strong>
                {metric === 'points'
                  ? `${entry.points} points`
                  : `${entry.validReports} valid reports`}
              </strong>
            </article>
          ))}
        </div>

        <section className="leaderboard-table-panel">
          <header>
            <div>
              <h2>Community ranking</h2>
              <p>Only administrator-validated reports count toward the ranking.</p>
            </div>
            <span>Updated daily</span>
          </header>
          <div className="leaderboard-table-wrap">
            <table className="leaderboard-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Member</th>
                  <th>Title</th>
                  <th>Valid reports</th>
                  <th>Points</th>
                </tr>
              </thead>
              <tbody>
                {rankedEntries.map((entry, index) => (
                  <tr
                    className={entry.isCurrentUser ? 'leaderboard-table__current' : ''}
                    key={entry.id}
                  >
                    <td><strong>#{index + 1}</strong></td>
                    <td>
                      <span className="leaderboard-member">
                        <span>{entry.name.split(' ').map((part) => part[0]).join('')}</span>
                        <strong>{entry.name}</strong>
                        {entry.isCurrentUser && <small>You</small>}
                      </span>
                    </td>
                    <td>{entry.title}</td>
                    <td>{entry.validReports}</td>
                    <td><strong>{entry.points}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </section>
  )
}
