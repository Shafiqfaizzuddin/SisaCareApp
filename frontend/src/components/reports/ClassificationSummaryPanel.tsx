import type { ClassificationSummary } from '../../types'

export function ClassificationSummaryPanel({ summary, original = true }: { summary: ClassificationSummary; original?: boolean }) {
  return <section className="classification-summary" aria-label="Waste material analysis">
    <h3>{original ? 'Original photo analysis' : 'Photo analysis'}</h3>
    <p className="field__hint">Florence-2 supplied candidate objects and boxes. Material categories and severity are rule-based estimates from those observations. Citizen corrections are recorded separately; administrator verification occurs after submission.</p>
    <div className="classification-summary__highlights">
      <div><small>Dominant material category</small><strong>{summary.dominant_category}</strong><span>{summary.dominant_reason}</span></div>
      <div><small>Estimated handling severity</small><strong>{summary.severity.level}</strong><span>{summary.severity.reason}</span></div>
    </div>
    <h4>Category distribution</h4>
    <p className="field__hint">{summary.denominator_definition} Denominator: {summary.denominator} observations; {summary.background_excluded} background detections excluded. These percentages are detection shares, not confidence, mass, volume, or image area.</p>
    {summary.denominator === 0 ? <p>No reportable detection evidence is available for a distribution.</p>
      : <ul className="classification-summary__distribution">{summary.distribution.map(entry => <li key={entry.category}>
        <div><strong>{entry.category}</strong><span>{entry.count} / {summary.denominator} · {entry.percentage.toFixed(1)}%</span></div>
        <div className="classification-summary__track" aria-hidden="true"><span style={{ width: `${entry.percentage}%` }} /></div>
      </li>)}</ul>}
    {(summary.unknown_count > 0 || summary.uncertain_count > 0) && <p role="status" className="classification-summary__uncertainty">
      {summary.unknown_count} observations have Unknown material category; {summary.uncertain_count} need further confirmation.</p>}
    <p className="field__hint"><strong>Confidence:</strong> {summary.confidence.explanation}</p>
  </section>
}
