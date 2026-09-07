import {
  ArrowRight,
  Award,
  CheckCircle2,
  ClipboardCheck,
  MapPin,
  Sprout,
  Trophy,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { PageIntro } from '../components/common/PageIntro'
import { getMyImpact } from '../features/authentication/reward-api'
import { useRole } from '../features/authentication/useRole'

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-MY').format(value)
}

export function MyImpactPage() {
  const { user } = useRole()
  const impactQuery = useQuery({
    queryKey: ['my-impact', user?.id],
    queryFn: getMyImpact,
    enabled: Boolean(user),
  })

  const impact = impactQuery.data

  return (
    <section className="section member-page impact-page">
      <div className="container">
        <PageIntro
          eyebrow="My Impact"
          title="Your Community Impact"
          description="A clearer view of the verified reports, resolved cases, active locations, and achievements connected to your SisaCare contributions."
          actions={
            <Link className="button button--primary" to="/report">
              Submit report <ArrowRight size={17} />
            </Link>
          }
        />

        {impactQuery.isLoading && <p className="empty-state">Loading your impact...</p>}
        {impactQuery.isError && <p className="form-error">Your impact summary could not be loaded.</p>}

        {impact && (
          <>
            <section className="impact-summary" aria-label="Your community impact summary">
              <article>
                <span><ClipboardCheck size={22} /></span>
                <strong>{formatNumber(impact.verifiedReports)}</strong>
                <p>verified reports</p>
              </article>
              <article>
                <span><CheckCircle2 size={22} /></span>
                <strong>{formatNumber(impact.casesResolved)}</strong>
                <p>cases resolved</p>
              </article>
              <article>
                <span><MapPin size={22} /></span>
                <strong>{formatNumber(impact.locationsCurrentlyHandled)}</strong>
                <p>locations currently being handled</p>
              </article>
              <article>
                <span><Sprout size={22} /></span>
                <strong>{formatNumber(impact.achievementsUnlocked)}</strong>
                <p>achievements unlocked</p>
              </article>
            </section>

            <section className="impact-title-panel">
              <div>
                <span><Trophy size={24} /></span>
                <div>
                  <p className="eyebrow">Current title</p>
                  <h2>{impact.currentTitle}</h2>
                </div>
              </div>
              <dl>
                <div>
                  <dt>Total points</dt>
                  <dd>{formatNumber(impact.totalPoints)}</dd>
                </div>
                <div>
                  <dt>Unread impact updates</dt>
                  <dd>{formatNumber(impact.unreadImpactNotifications)}</dd>
                </div>
              </dl>
            </section>

            <section className="impact-next-steps">
              <div>
                <Award size={20} />
                <h2>Next milestone</h2>
                <p>
                  Keep submitting clear photos with accurate locations. Verified
                  reports and completed municipal cases move your impact forward.
                </p>
              </div>
              <Link to="/account">
                View rewards history <ArrowRight size={16} />
              </Link>
            </section>
          </>
        )}
      </div>
    </section>
  )
}
