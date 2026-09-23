import {
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Download,
  Search,
  TriangleAlert,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { MetricCard } from '../components/admin/MetricCard'
import { ReportStatus } from '../components/reports/ReportStatus'
import { reportSummaries } from '../features/admin-reports/report-data'
import { fetchPersistedReports } from '../features/admin-reports/admin-reports-api'
import { wasteCategoryOptions } from '../features/reporting/categories'
import type { ReportStatus as ReportStatusValue, WasteCategory } from '../types'

const categoryLabels = Object.fromEntries(
  wasteCategoryOptions.map((category) => [category.value, category.label]),
) as Record<WasteCategory, string>

type StatusFilter = 'all' | ReportStatusValue

export function AdminDashboardPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [persistedReports, setPersistedReports] = useState<typeof reportSummaries>([])

  useEffect(() => {
    const controller = new AbortController()
    fetchPersistedReports(controller.signal)
      .then(setPersistedReports)
      .catch(() => undefined)
    return () => controller.abort()
  }, [])

  const availableReports = useMemo(() => {
    const persistedIds = new Set(persistedReports.map((report) => report.id))
    return [
      ...persistedReports,
      ...reportSummaries.filter((report) => !persistedIds.has(report.id)),
    ]
  }, [persistedReports])

  const filteredReports = useMemo(() => {
    const query = search.trim().toLowerCase()

    return availableReports.filter((report) => {
      const matchesSearch =
        !query ||
        report.reference.toLowerCase().includes(query) ||
        report.location.toLowerCase().includes(query)
      const matchesStatus = status === 'all' || report.status === status

      return matchesSearch && matchesStatus
    })
  }, [availableReports, search, status])

  function downloadCsv() {
    const header = ['Reference', 'Category', 'Location', 'Submitted', 'Status']
    const rows = filteredReports.map((report) => [
      report.reference,
      categoryLabels[report.category],
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
          <p className="eyebrow">Saturday, 8 August</p>
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
          value="18"
          detail="+4 since yesterday"
          icon={TriangleAlert}
          tone="coral"
        />
        <MetricCard
          label="In progress"
          value="42"
          detail="7 due for review"
          icon={Clock3}
          tone="amber"
        />
        <MetricCard
          label="Resolved this week"
          value="67"
          detail="12% above average"
          icon={CheckCircle2}
          tone="green"
        />
        <MetricCard
          label="Median response"
          value="19h"
          detail="3h faster this month"
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
              aria-label="Filter by status"
              value={status}
              onChange={(event) => setStatus(event.target.value as StatusFilter)}
            >
              <option value="all">All statuses</option>
              <option value="processing">Processing</option>
              <option value="in_progress">In progress</option>
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
                        {report.reporterRole === 'user' ? 'Member' : 'Guest'}
                      </small>
                    </span>
                  </td>
                  <td>{categoryLabels[report.category]}</td>
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
          {filteredReports.length === 0 && (
            <p className="empty-state">No reports match the current filters.</p>
          )}
        </div>
      </section>
    </>
  )
}
