import {
  ArrowRight,
  Camera,
  CheckCircle2,
  Clock3,
  MapPin,
  ShieldCheck,
} from 'lucide-react'
import { Link } from 'react-router-dom'

const cleanupImage =
  'https://images.unsplash.com/photo-1758599668924-02f56a9aacc2?auto=format&fit=crop&w=1400&q=82'

export function HomePage() {
  return (
    <>
      <section className="home-hero">
        <div className="container home-hero__grid">
          <div className="home-hero__content">
            <p className="eyebrow">Community waste reporting</p>
            <h1>Report illegal dumping. Protect your neighbourhood.</h1>
            <p className="home-hero__lead">
              Send clear evidence and location details to help local teams assess
              waste sites and coordinate a faster response.
            </p>
            <div className="home-hero__actions">
              <Link className="button button--primary" to="/report">
                <Camera size={18} />
                Report waste
              </Link>
              <Link className="button button--secondary" to="/education">
                Learn what to report
                <ArrowRight size={17} />
              </Link>
            </div>
            <div className="home-hero__assurance">
              <span>
                <ShieldCheck size={17} /> Secure reporting
              </span>
              <span>
                <Clock3 size={17} /> Takes about 3 minutes
              </span>
            </div>
          </div>

          <figure className="home-hero__visual">
            <img
              src={cleanupImage}
              alt="Volunteers collecting litter together near a shoreline"
            />
            <figcaption>
              <span className="home-hero__visual-icon">
                <CheckCircle2 size={18} />
              </span>
              <span>
                <strong>Community action starts with a clear report</strong>
                Photos and accurate locations help teams prioritise safely.
              </span>
            </figcaption>
          </figure>
        </div>
      </section>

      <section className="impact-band" aria-label="Service impact">
        <div className="container impact-band__grid">
          <div>
            <strong>1,248</strong>
            <span>reports received</span>
          </div>
          <div>
            <strong>82%</strong>
            <span>reviewed within 24 hours</span>
          </div>
          <div>
            <strong>936</strong>
            <span>sites resolved</span>
          </div>
          <div>
            <strong>4.8/5</strong>
            <span>community satisfaction</span>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="section-heading">
            <div>
              <p className="eyebrow">A clearer response</p>
              <h2>Three steps from sighting to action</h2>
            </div>
            <p>
              Good evidence helps municipal teams understand the site before they
              arrive.
            </p>
          </div>
          <div className="process-grid">
            <article className="process-card">
              <span>01</span>
              <div className="process-card__icon">
                <Camera size={21} />
              </div>
              <h3>Capture the site</h3>
              <p>Take a clear photo from a safe distance without moving any waste.</p>
            </article>
            <article className="process-card">
              <span>02</span>
              <div className="process-card__icon process-card__icon--amber">
                <MapPin size={21} />
              </div>
              <h3>Confirm the location</h3>
              <p>Add an address or landmark so the response team can find it.</p>
            </article>
            <article className="process-card">
              <span>03</span>
              <div className="process-card__icon process-card__icon--blue">
                <CheckCircle2 size={21} />
              </div>
              <h3>Track the response</h3>
              <p>Keep your reference number to check progress after submission.</p>
            </article>
          </div>
        </div>
      </section>

      <section className="section section--muted">
        <div className="container action-band">
          <div>
            <p className="eyebrow">Not sure what you found?</p>
            <h2>Identify waste before you approach it.</h2>
            <p>
              Learn the common categories and when unknown materials should be
              left for trained personnel.
            </p>
          </div>
          <Link className="button button--secondary" to="/education">
            Open waste guide
            <ArrowRight size={17} />
          </Link>
        </div>
      </section>
    </>
  )
}
