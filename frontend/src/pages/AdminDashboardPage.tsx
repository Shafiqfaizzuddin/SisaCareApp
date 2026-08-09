import {
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Download,
  Search,
  TriangleAlert,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { MetricCard } from '../components/admin/MetricCard'
import { ReportStatus } from '../components/reports/ReportStatus'
import { wasteCategoryOptions } from '../features/reporting/categories'
import {
  formatReportDate,
  getAdminReports,
} from '../features/reporting/report-api'
import type { ReportStatus as ReportStatusValue, WasteCategory } from '../types'

const categoryLabels = Object.fromEntries(
  wasteCategoryOptions.map((category) => [category.value, category.label]),
) as Record<WasteCategory, string>

type StatusFilter = 'all' | ReportStatusValue

export function AdminDashboardPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const reportsQuery = useQuery({
    queryKey: ['admin-reports'],
    queryFn: getAdminReports,
  })
  const reports = useMemo(() => reportsQuery.data ?? [], [reportsQuery.data])

  const filteredReports = useMemo(() => {
    const query = search.trim().toLowerCase()

    return reports.filter((report) => {
      const matchesSearch =
        !query ||
        report.reference.toLowerCase().includes(query) ||
        report.location.toLowerCase().includes(query)
      const matchesStatus = status === 'all' || report.status === status

      return matchesSearch && matchesStatus
    })
  }, [reports, search, status])

  const pendingCount = reports.filter(
    (report) => report.validationStatus === 'pending',
  ).length
  const inProgressCount = reports.filter(
    (report) => report.status === 'in_progress',
  ).length
  const completedCount = reports.filter(
    (report) => report.status === 'completed',
  ).length
  const validCount = reports.filter(
    (report) => report.validationStatus === 'valid',
  ).length

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
          <p className="eyebrow">
            {new Intl.DateTimeFormat('en-MY', { dateStyle: 'full' }).format(new Date())}
          </p>
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
          value={String(pendingCount)}
          detail="Awaiting validation"
          icon={TriangleAlert}
          tone="coral"
        />
        <MetricCard
          label="In progress"
          value={String(inProgressCount)}
          detail="Active municipal cases"
          icon={Clock3}
          tone="amber"
        />
        <MetricCard
          label="Completed"
          value={String(completedCount)}
          detail="Closed cases"
          icon={CheckCircle2}
          tone="green"
        />
        <MetricCard
          label="Validated"
          value={String(validCount)}
          detail="Confirmed reports"
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
                  <td>{formatReportDate(report.submittedAt)}</td>
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
            <p className="empty-state">
              {reportsQuery.isLoading
                ? 'Loading reports...'
                : reportsQuery.isError
                  ? 'Reports could not be loaded. Check your administrator access.'
                  : 'No reports match the current filters.'}
            </p>
          )}
        </div>
      </section>
    </>
  )
}
