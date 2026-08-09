import { AlertTriangle, Camera, MapPin, ShieldAlert } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { WasteGuideCard } from '../components/education/WasteGuideCard'
import { PageIntro } from '../components/common/PageIntro'
import { getPublishedEducation } from '../features/education/education-api'

export function EducationPage() {
  const contentQuery = useQuery({
    queryKey: ['published-education'],
    queryFn: getPublishedEducation,
  })

  return (
    <>
      <section className="section education-page">
        <div className="container">
          <PageIntro
            eyebrow="Waste guide"
            title="Know what you are reporting"
            description="Recognise common waste types, choose safer disposal options, and leave hazardous materials for trained personnel."
          />
          <div className="guide-grid">
            {(contentQuery.data ?? []).map((topic) => (
              <WasteGuideCard key={topic.id} topic={topic} />
            ))}
          </div>
          {contentQuery.isLoading && <p className="empty-state">Loading published guidance...</p>}
          {contentQuery.isError && <p className="form-error">Educational content could not be loaded.</p>}
          {!contentQuery.isLoading && contentQuery.data?.length === 0 && (
            <p className="empty-state">No educational guidance has been published yet.</p>
          )}
        </div>
      </section>

      <section className="section section--dark">
        <div className="container safety-layout">
          <div>
            <p className="eyebrow">Safety first</p>
            <h2>Never handle suspicious or hazardous waste.</h2>
            <p>
              Keep people away from leaking containers, sharp materials, smoke,
              chemical smells, or medical waste. Use emergency services when
              there is an immediate threat to people or property.
            </p>
          </div>
          <div className="safety-list">
            <div>
              <ShieldAlert size={21} />
              <span>
                <strong>Keep your distance</strong>
                Do not open, move, or smell unknown containers.
              </span>
            </div>
            <div>
              <AlertTriangle size={21} />
              <span>
                <strong>Warn others nearby</strong>
                Prevent children and pets from approaching the site.
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container evidence-guide">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Better evidence</p>
              <h2>Capture useful details without getting closer.</h2>
            </div>
          </div>
          <div className="evidence-guide__items">
            <article>
              <Camera size={21} />
              <h3>Frame the whole site</h3>
              <p>Show the scale of the waste and the surrounding access area.</p>
            </article>
            <article>
              <MapPin size={21} />
              <h3>Include a landmark</h3>
              <p>Road signs, building names, and junctions help verify location.</p>
            </article>
            <article>
              <ShieldAlert size={21} />
              <h3>Describe hazards</h3>
              <p>Note smoke, liquids, sharp objects, traffic, or blocked pathways.</p>
            </article>
          </div>
        </div>
      </section>
    </>
  )
}
