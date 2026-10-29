import { useEffect, useState } from 'react'
import { PageIntro } from '../components/common/PageIntro'
import { fetchLearnArticles, type LearnArticle } from '../features/education/education-api'

export function EducationPage() {
  const [articles, setArticles] = useState<LearnArticle[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void fetchLearnArticles(controller.signal).then(setArticles)
      .catch(value => { if (!controller.signal.aborted) setError(value instanceof Error ? value.message : 'Learning content is unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [revision])

  return <section className="section education-page">
    <div className="container">
      <PageIntro eyebrow="Learn" title="Solid waste and recycling knowledge"
        description="Practical information shared by the SisaCare.AI administrators. Check local collection requirements before disposing of materials." />
      {loading && <p role="status">Loading learning content...</p>}
      {error && <div role="alert" className="learn-error"><p>{error}</p><button type="button" className="button button--secondary" onClick={() => { setError(''); setLoading(true); setRevision(value => value + 1) }}>Retry</button></div>}
      {!loading && !error && articles.length === 0 && <p>No learning articles have been published yet.</p>}
      {!loading && !error && <div className="learn-grid">{articles.map(article =>
        <article className="learn-card" key={article.id}>
          {article.image_url && <img src={article.image_url} alt={article.image_alt} loading="lazy" />}
          <div className="learn-card__content">
            <h2>{article.title}</h2>
            <p className="learn-card__summary">{article.summary}</p>
            <p className="learn-card__body">{article.body}</p>
          </div>
        </article>)}</div>}
    </div>
  </section>
}
