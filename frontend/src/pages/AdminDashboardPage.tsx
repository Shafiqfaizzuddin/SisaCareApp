import { ArrowUpRight, CheckCircle2, Clock3, Download, Search, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { MetricCard } from '../components/admin/MetricCard'
import { ReportStatus } from '../components/reports/ReportStatus'
import { fetchPersistedReports } from '../features/admin-reports/admin-reports-api'
import { wasteCategoryOptions } from '../features/reporting/categories'
import type { ReportStatus as ReportStatusValue, ReportSummary, WasteCategory } from '../types'

const categoryLabels = Object.fromEntries(
  wasteCategoryOptions.map((category) => [category.value, category.label]),
) as Record<WasteCategory, string>

type StatusFilter = 'all' | ReportStatusValue
type CategoryFilter = 'all' | WasteCategory

export function AdminDashboardPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [persistedReports, setPersistedReports] = useState<ReportSummary[]>([])
  const [loadError, setLoadError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshVersion, setRefreshVersion] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    fetchPersistedReports(controller.signal)
      .then(reports => { setPersistedReports(reports); setLoadError('') })
      .catch(error => { if (!controller.signal.aborted) setLoadError(error instanceof Error ? error.message : 'Reports could not be loaded.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [refreshVersion])

  const availableReports = useMemo(() => {
    return persistedReports
  }, [persistedReports])

  const filteredReports = useMemo(() => {
    const query = search.trim().toLowerCase()

    return availableReports.filter((report) => {
      const matchesSearch =
        !query ||
        report.reference.toLowerCase().includes(query) ||
        report.location.toLowerCase().includes(query)
      const matchesStatus = status === 'all' || report.status === status
      const matchesCategory = category === 'all' || report.category === category

      return matchesSearch && matchesStatus && matchesCategory
    })
  }, [availableReports, search, status, category])

  function downloadCsv() {
    const header = ['Reference', 'Category', 'Location', 'Submitted', 'Status']
    const rows = filteredReports.map((report) => [
      report.reference,
      categoryLabels[report.category] ?? report.category,
      report.location,
      report.submittedAt,
      report.status,
    ])
    const csv = [header, ...rows]
      .map((row) => row.map((value) => `"${value.replaceAll('"', '""')}"`).join(','))
      .join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'sisacare-reports.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">Municipal review queue</p>
          <h1>Operations overview</h1>
          <p>Review new reports and monitor active response work.</p>
        </div>
        <button className="button button--secondary" type="button" onClick={downloadCsv}>
          <Download size={17} />
          Export CSV
        </button>
      </header>

      <section className="metric-grid" aria-label="Report metrics">
        <MetricCard
          label="New reports"
          value={String(availableReports.filter(report => report.status === 'submitted').length)}
          detail="Awaiting verification"
          icon={TriangleAlert}
          tone="coral"
        />
        <MetricCard
          label="In progress"
          value={String(availableReports.filter(report => report.status === 'in_progress').length)}
          detail="Assigned reports"
          icon={Clock3}
          tone="amber"
        />
        <MetricCard
          label="Resolved reports"
          value={String(availableReports.filter(report => report.status === 'resolved').length)}
          detail="All time"
          icon={CheckCircle2}
          tone="green"
        />
        <MetricCard
          label="Verified reports"
          value={String(availableReports.filter(report => report.status === 'verified').length)}
          detail="Ready for assignment"
          icon={ArrowUpRight}
          tone="blue"
        />
      </section>

      <section className="admin-panel report-list">
        <header className="admin-panel__heading">
          <div>
            <h2>Recent reports</h2>
            <p>{filteredReports.length} reports shown</p>
          </div>
          <div className="report-filters">
            <label className="search-field">
              <Search size={17} />
              <input
                aria-label="Search reports"
                placeholder="Search reference or location"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <select
              aria-label="Filter by category"
              value={category}
              onChange={(event) => setCategory(event.target.value as CategoryFilter)}
            >
              <option value="all">All categories</option>
              {wasteCategoryOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <select
              aria-label="Filter by status"
              value={status}
              onChange={(event) => setStatus(event.target.value as StatusFilter)}
            >
              <option value="all">All statuses</option>
              <option value="submitted">Submitted</option>
              <option value="verified">Verified</option>
              <option value="processing">Processing</option>
              <option value="in_progress">In progress</option>
              <option value="resolved">Resolved</option>
              <option value="rejected">Rejected</option>
              <option value="completed">Completed</option>
            </select>
          </div>
        </header>

        <div className="report-table-wrap">
          <table className="report-table">
            <thead>
              <tr>
                <th>Report</th>
                <th>Category</th>
                <th>Location</th>
                <th>Submitted</th>
                <th>Status</th>
                <th><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {filteredReports.map((report) => (
                <tr key={report.id}>
                  <td>
                    <span className="report-identity">
                      <strong>{report.reference}</strong>
                      <small>
                        {report.reporterRole === 'user' ? 'Community User' : 'Legacy guest'}
                      </small>
                    </span>
                  </td>
                  <td>{categoryLabels[report.category] ?? report.category}</td>
                  <td className="report-table__location">{report.location}</td>
                  <td>{report.submittedAt}</td>
                  <td><ReportStatus status={report.status} /></td>
                  <td>
                    <Link
                      className="icon-button"
                      to={`/admin/reports/${report.id}`}
                      aria-label={`Open report ${report.reference}`}
                      title="Open report"
                    >
                      <ArrowUpRight size={17} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading && <p className="empty-state">Loading reports...</p>}
          {loadError && <div className="empty-state" role="alert">{loadError} <button type="button" onClick={() => setRefreshVersion(value => value + 1)}>Try again</button></div>}
          {!loading && !loadError && filteredReports.length === 0 && (
            <p className="empty-state">No reports match the current filters.</p>
          )}
        </div>
      </section>
    </>
  )
}
