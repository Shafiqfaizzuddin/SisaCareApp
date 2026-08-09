import { Award, Crown, Medal, ShieldCheck, Trophy } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { PageIntro } from '../components/common/PageIntro'
import { getLeaderboard } from '../features/authentication/reward-api'
import { useRole } from '../features/authentication/useRole'

type LeaderboardMetric = 'points' | 'reports'

export function LeaderboardPage() {
  const [metric, setMetric] = useState<LeaderboardMetric>('points')
  const { user } = useRole()
  const leaderboardQuery = useQuery({
    queryKey: ['leaderboard'],
    queryFn: getLeaderboard,
  })
  const rankedEntries = useMemo(
    () => {
      const entries = (leaderboardQuery.data ?? []).map((entry) => ({
        ...entry,
        isCurrentUser: entry.id === user?.id,
      }))
      return entries
        .sort((a, b) =>
          metric === 'points'
            ? b.points - a.points
            : b.validReports - a.validReports,
        )
    },
    [leaderboardQuery.data, metric, user?.id],
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

        {leaderboardQuery.isLoading && <p className="empty-state">Loading community rankings...</p>}
        {leaderboardQuery.isError && <p className="form-error">The leaderboard could not be loaded.</p>}

        <section className="leaderboard-table-panel">
          <header>
            <div>
              <h2>Community ranking</h2>
              <p>Only administrator-validated reports count toward the ranking.</p>
            </div>
            <span>Live rankings</span>
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
          {!leaderboardQuery.isLoading && rankedEntries.length === 0 && (
            <p className="empty-state">No registered contributors are ranked yet.</p>
          )}
        </section>
      </div>
    </section>
  )
}
