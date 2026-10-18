import { Award, Crown, Medal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { PageIntro } from '../components/common/PageIntro'
import { useRole } from '../features/authentication/useRole'
import { memberTitleForPoints } from '../features/authentication/member-data'
import type { LeaderboardEntry } from '../types'

type RankedEntry = LeaderboardEntry & { rank: number }

export function LeaderboardPage() {
  const { user } = useRole()
  const [entries, setEntries] = useState<RankedEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(0)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    void fetch(`/api/members/leaderboard?limit=50&offset=${page * 50}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Leaderboard could not be loaded.')
        const value: unknown = await response.json()
        if (!value || typeof value !== 'object' || !('entries' in value) || !Array.isArray(value.entries)
          || !('total' in value) || typeof value.total !== 'number') throw new Error('Leaderboard returned invalid data.')
        const rows = value.entries.map((entry: unknown) => {
          if (!entry || typeof entry !== 'object' || !('id' in entry) || typeof entry.id !== 'string'
            || !('name' in entry) || typeof entry.name !== 'string' || !('points' in entry) || typeof entry.points !== 'number'
            || !('valid_reports' in entry) || typeof entry.valid_reports !== 'number'
            || !('rank' in entry) || typeof entry.rank !== 'number') throw new Error('Leaderboard returned invalid data.')
          return { id: entry.id, name: entry.name, points: entry.points,
            validReports: entry.valid_reports, rank: entry.rank, title: memberTitleForPoints(entry.points) }
        })
        if (!controller.signal.aborted) { setEntries(rows); setTotal(value.total) }
      })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Leaderboard could not be loaded.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [page, version])

  return <section className="section leaderboard-page"><div className="container">
    <PageIntro eyebrow="Community rewards" title="SisaCare leaderboard"
      description="Ranked by verified lifetime Eco Points from approved reports and recycling actions." />
    {user?.rank && <p role="status">Your current rank: #{user.rank}</p>}
    {loading ? <p role="status">Loading real participant rankings…</p> : error ?
      <div role="alert"><p>{error}</p><button type="button" className="button button--secondary" onClick={() => setVersion(value => value + 1)}>Try again</button></div> :
      entries.length === 0 ? <p className="empty-state">No eligible verified activity yet.</p> : <>
      {page === 0 && <div className="leaderboard-podium">{entries.slice(0, 3).map(entry => <article className={`podium-card podium-card--${entry.rank}`} key={entry.id}>
        <span className="podium-card__rank">{entry.rank === 1 ? <Crown size={21} /> : <Medal size={20} />}</span>
        <div className="podium-card__avatar">{entry.name.split(' ').map(part => part[0]).join('')}</div>
        <span>#{entry.rank}</span><h2>{entry.name}</h2><p><Award size={14} /> {entry.title}</p>
        <strong>{entry.points} points</strong></article>)}</div>}
      <section className="leaderboard-table-panel"><header><div><h2>Community ranking</h2><p>Verified lifetime contributions; ties share a rank.</p></div><span>{total} participants</span></header>
        <div className="leaderboard-table-wrap"><table className="leaderboard-table"><thead><tr><th>Rank</th><th>Member</th><th>Title</th><th>Valid reports</th><th>Points</th></tr></thead>
          <tbody>{entries.map(entry => <tr className={entry.id === user?.id ? 'leaderboard-table__current' : ''} key={entry.id}>
            <td><strong>#{entry.rank}</strong></td><td><span className="leaderboard-member"><span>{entry.name.split(' ').map(part => part[0]).join('')}</span><strong>{entry.name}</strong>{entry.id === user?.id && <small>You</small>}</span></td>
            <td>{entry.title}</td><td>{entry.validReports}</td><td><strong>{entry.points}</strong></td></tr>)}</tbody></table></div>
        <div className="form-actions">{page > 0 && <button type="button" className="button button--secondary" onClick={() => setPage(value => value - 1)}>Previous</button>}
          {(page + 1) * 50 < total && <button type="button" className="button button--secondary" onClick={() => setPage(value => value + 1)}>Next</button>}</div>
      </section></>}
  </div></section>
}
