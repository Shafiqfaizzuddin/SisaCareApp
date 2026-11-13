import { ArrowUpRight, CheckCircle2, Clock3, Download, Search, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { MetricCard } from '../components/admin/MetricCard'
import { EmailDeliveryPanel } from '../components/admin/EmailDeliveryPanel'
import { AdminNotificationPanel } from '../components/admin/AdminNotificationPanel'
import { AppDataTable, Column } from '../components/common/AppDataTable'
import { GoogleMap, OBSERVED_DENSITY_BANDS } from '../components/location/GoogleMap'
import { ReportStatus } from '../components/reports/ReportStatus'
import { downloadAnalytics, fetchAnalytics, fetchForecast } from '../features/admin-analytics/admin-analytics-api'
import type { Analytics, AnalyticsFilters, Forecast } from '../features/admin-analytics/admin-analytics-api'
import { fetchPersistedReports } from '../features/admin-reports/admin-reports-api'
import { wasteCategoryOptions } from '../features/reporting/categories'
import type { ReportStatus as ReportStatusValue, ReportSummary, WasteCategory } from '../types'

const categoryLabels = Object.fromEntries(
  wasteCategoryOptions.map((category) => [category.value, category.label]),
) as Record<WasteCategory, string>

type StatusFilter = 'all' | ReportStatusValue
type CategoryFilter = 'all' | WasteCategory

export function AdminDashboardPage() {
  const location = useLocation()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [persistedReports, setPersistedReports] = useState<ReportSummary[]>([])
  const [loadError, setLoadError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [area, setArea] = useState('')
  const [provenance, setProvenance] = useState<AnalyticsFilters['provenance']>('production')
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [analyticsError, setAnalyticsError] = useState('')
  const [areaOptions, setAreaOptions] = useState<string[]>([])
  const [forecast, setForecast] = useState<Forecast | null>(null)
  const [layer, setLayer] = useState<'observed' | 'forecast'>('observed')
  const [selectedCellKey, setSelectedCellKey] = useState('')
  const [periodIndex, setPeriodIndex] = useState(0)
  const [exportError, setExportError] = useState('')

  useEffect(() => {
    if (location.hash === '#reports') {
      document.getElementById('reports')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    }
  }, [location.hash])

  const filters = useMemo<AnalyticsFilters>(() => ({ start, end,
    category: category === 'all' ? '' : category, status: status === 'all' ? '' : status,
    area, provenance }), [start, end, category, status, area, provenance])

  useEffect(() => {
    const controller = new AbortController()
    setAnalytics(null)
    fetchAnalytics(filters, controller.signal)
      .then(result => { setAnalytics(result); setAnalyticsError('')
        if (!area) setAreaOptions(result.observed_heatmap.map(cell => cell.cell_key)) })
      .catch(error => { if (!controller.signal.aborted) setAnalyticsError(error instanceof Error ? error.message : 'Analytics unavailable.') })
    return () => controller.abort()
  }, [filters, area])

  useEffect(() => {
    const controller = new AbortController()
    setForecast(null)
    if (provenance === 'legacy_unknown') { setForecast(null); return () => controller.abort() }
    fetchForecast(provenance === 'demo' ? 'synthetic_demo' : 'production', controller.signal)
      .then(setForecast).catch(() => { if (!controller.signal.aborted) setForecast(null) })
    return () => controller.abort()
  }, [provenance])

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

  async function exportFile(format: 'csv' | 'pdf') {
    try { await downloadAnalytics(format, filters); setExportError('') }
    catch (error) { setExportError(error instanceof Error ? error.message : 'Export unavailable.') }
  }

  const metrics = analytics?.metrics
  const forecastPeriod = forecast?.periods[periodIndex]
  const heatPoints = useMemo(() => layer === 'observed'
    ? (analytics?.observed_heatmap ?? []).map(cell => ({ latitude: cell.center_latitude, longitude: cell.center_longitude,
      weight: cell.count, cellKey: cell.cell_key,
      bounds: { south: cell.south, north: cell.north, west: cell.west, east: cell.east } }))
    : (forecastPeriod?.cells ?? []).map(cell => ({ latitude: cell.center_latitude,
      longitude: cell.center_longitude, weight: cell.predicted_count })),
    [layer, analytics?.observed_heatmap, forecastPeriod?.cells])
  const selectedCell = analytics?.observed_heatmap.find(cell => cell.cell_key === selectedCellKey)
  const mappedReportCount = (analytics?.observed_heatmap ?? []).reduce((sum, cell) => sum + cell.count, 0)
  const displayCount = (value: number | null | undefined, suffix = '') => value == null ? 'Unavailable' : `${value}${suffix}`
  const trendPeak = Math.max(1, ...(analytics?.trends ?? []).slice(-30).flatMap(day => [day.reported, day.resolved]))
  const mapRows = (layer === 'observed' ? (analytics?.observed_heatmap ?? []).map(cell => ({ key: cell.cell_key, count: cell.count }))
    : (forecastPeriod?.cells ?? []).map(cell => ({ key: cell.cell_key, count: cell.predicted_count })))
    .sort((a, b) => b.count - a.count).slice(0, 20)

  return (
    <>
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">Municipal review queue</p>
          <h1>Operations overview</h1>
          <p>Review new reports and monitor active response work.</p>
        </div>
        <div className="analytics-actions">
          <button className="button button--secondary" type="button" onClick={() => void exportFile('csv')}><Download size={17} /> Export CSV</button>
          <button className="button button--secondary" type="button" onClick={() => void exportFile('pdf')}><Download size={17} /> Export PDF</button>
        </div>
      </header>

      <section className="admin-panel analytics-panel" aria-label="Analytics filters">
        <div className="analytics-filters">
          <label>From (UTC)<input type="date" value={start} onChange={event => setStart(event.target.value)} /></label>
          <label>To (UTC)<input type="date" value={end} onChange={event => setEnd(event.target.value)} /></label>
          <label>Filter by category<select aria-label="Filter by category" value={category} onChange={event => setCategory(event.target.value as CategoryFilter)}>
            <option value="all">All categories</option>{wasteCategoryOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          <label>Filter by status<select aria-label="Filter by status" value={status} onChange={event => setStatus(event.target.value as StatusFilter)}>
            <option value="all">All statuses</option>{['submitted', 'verified', 'assigned', 'processing', 'in_progress', 'pending_verification', 'resolved', 'rejected', 'completed'].map(option =>
              <option key={option} value={option}>{option.replaceAll('_', ' ')}</option>)}</select></label>
          <label>Data source<select value={provenance} onChange={event => { setProvenance(event.target.value as AnalyticsFilters['provenance']); setArea(''); setLayer('observed') }}>
            <option value="production">Observed production reports</option><option value="legacy_unknown">Legacy, provenance unknown</option><option value="demo">Demonstration reports</option>
          </select></label>
          <label>Observed 1 km area<select value={area} onChange={event => { setArea(event.target.value); setSelectedCellKey('') }}><option value="">All areas</option>
            {areaOptions.map(key => <option key={key} value={key}>{key}</option>)}</select></label>
        </div>
        <p>These filters apply to analytics, the observed map, and exports. Category and status also filter the review list below.</p>
        {analytics?.generated_at && <p>Calculated {new Date(analytics.generated_at).toLocaleString()} from {analytics.filters.provenance} reports.</p>}
        {analyticsError && <p role="alert">{analyticsError}</p>}
        {exportError && <p role="alert">{exportError}</p>}
      </section>

      <section className="metric-grid" aria-label="Report metrics">
        <MetricCard
          label="Submitted reports"
          value={displayCount(metrics?.total_submitted)}
          detail="Selected submission cohort"
          icon={TriangleAlert}
          tone="coral"
        />
        <MetricCard
          label="Resolution rate"
          value={displayCount(metrics?.resolution_rate_percent, '%')}
          detail="Currently resolved / submitted"
          icon={Clock3}
          tone="amber"
        />
        <MetricCard
          label="Resolved reports"
          value={displayCount(metrics?.resolved_current)}
          detail="Current status is resolved"
          icon={CheckCircle2}
          tone="green"
        />
        <MetricCard
          label="Median resolution"
          value={displayCount(metrics?.median_resolution_hours, ' h')}
          detail={`Average ${displayCount(metrics?.average_resolution_hours, ' h')} · ${metrics?.verified_resolution_count ?? 0} verified`}
          icon={ArrowUpRight}
          tone="blue"
        />
      </section>

      <section className="analytics-grid">
        <div className="admin-panel"><h2>Report breakdown</h2>
          <h3>By status</h3><ul>{Object.entries(metrics?.by_status ?? {}).map(([name, count]) => <li key={name}>{name.replaceAll('_', ' ')}: <strong>{count}</strong></li>)}</ul>
          <h3>By waste category</h3><ul>{Object.entries(metrics?.by_category ?? {}).map(([name, count]) => <li key={name}>{name}: <strong>{count}</strong></li>)}</ul>
          {!metrics?.total_submitted && <p>No reports match these filters.</p>}
        </div>
        <div className="admin-panel"><h2>Staff collection</h2>
          <p>Assignments: <strong>{metrics?.staff.task_assignments ?? 0}</strong></p>
          <p>Active: <strong>{metrics?.staff.active_assignments ?? 0}</strong></p>
          <p>Verified completions with cleanup proof: <strong>{metrics?.staff.verified_completions_with_proof ?? 0}</strong></p>
          <div className="report-table-wrap"><AppDataTable data={metrics?.staff.by_staff ?? []} className="report-table" options={{ pageLength: 5 }}>
            <Column title="Staff ID" data="staff_id">{(id: string) => <span>{id.slice(0, 8)}…</span>}</Column>
            <Column title="Assigned" data="assigned" />
            <Column title="Active" data="active" />
            <Column title="Completed" data="verified_completions" />
          </AppDataTable></div>
        </div>
      </section>

      <section className="admin-panel analytics-panel"><h2>Reported vs. verified resolved</h2>
        <p>Dates use UTC. Resolutions for the selected submission cohort may occur after the selected end date.</p>
        <p>Green: reported · Orange: verified resolved · Chart maximum: {trendPeak} reports</p>
        <div className="analytics-trend" role="img" aria-label="Daily reported and verified resolved counts">
          {(analytics?.trends ?? []).slice(-30).map(day => <div key={day.date} className="analytics-trend__day" title={`${day.date}: ${day.reported} reported, ${day.resolved} resolved`}>
            <span style={{ height: `${day.reported ? Math.max(3, 80 * day.reported / trendPeak) : 0}px` }} /><span style={{ height: `${day.resolved ? Math.max(3, 80 * day.resolved / trendPeak) : 0}px` }} /><small>{day.date.slice(5)}</small>
          </div>)}
        </div>
        {!analytics?.trends.length && <p>No trend data for these filters.</p>}
      </section>

      <section className="admin-panel analytics-panel"><header className="admin-panel__heading"><div><h2>Waste density map</h2>
        <p>{layer === 'observed' ? `Observed ${provenance === 'production' ? 'production' : provenance} report counts` : `Modeled ${provenance === 'demo' ? 'synthetic demonstration' : 'production'} report counts`}</p></div>
        <div className="analytics-actions"><button type="button" className="button button--secondary" onClick={() => { setLayer('observed'); setSelectedCellKey('') }}>Observed</button>
          <button type="button" className="button button--secondary" disabled={provenance === 'legacy_unknown'} onClick={() => { setLayer('forecast'); setSelectedCellKey('') }}>Forecast</button></div></header>
        {layer === 'forecast' && <><p>Forecasts use coarser 0.05° cells and are trained on all report categories; category, status, submission date and observed 1 km area filters do not apply to this layer.</p>
          {provenance === 'demo' && <p>The synthetic forecast uses its own reproducible demonstration dataset; it is not derived from the observed demonstration reports on this page.</p>}
          {forecast?.status === 'available' ? <label>Forecast week <select value={periodIndex} onChange={event => setPeriodIndex(Number(event.target.value))}>
            {forecast.periods.map((period, index) => <option key={period.start} value={index}>{period.start.slice(0, 10)} to {period.end.slice(0, 10)}</option>)}</select></label>
            : <p role="status">{forecast?.status === 'insufficient_data' ? 'Forecast unavailable: insufficient training history.' : forecast?.reason ?? 'No forecast is available.'}</p>}</>}
        <GoogleMap location={null} heatPoints={heatPoints} heatTone={layer === 'observed' ? provenance === 'demo' ? 'demo' : 'observed' : provenance === 'demo' ? 'forecastDemo' : 'forecast'}
          onHeatCellSelect={layer === 'observed' ? setSelectedCellKey : undefined} showHeatControls
          ariaLabel={`${layer === 'observed' ? 'Observed report density' : 'Forecast report counts'} map`} />
        {layer === 'observed' ? <>
          <p>{mappedReportCount} reports in {(analytics?.observed_heatmap ?? []).length} mapped areas. Each shaded 1 km cell counts submitted reports in the selected filters. Colors represent report counts, not measured risk or severity. Demonstration cells have purple outlines. Exact report locations and reporter details are hidden. {metrics?.missing_coordinates ?? 0} selected reports have no usable map coordinates.</p>
          <div className="density-legend" aria-label="Observed report count legend">{OBSERVED_DENSITY_BANDS.map(band =>
            <span key={band.min}><i style={{ backgroundColor: band.color }} />{band.label}</span>)}</div>
          {selectedCell && <p role="status">Selected area {selectedCell.cell_key}: {selectedCell.count} {selectedCell.count === 1 ? 'report' : 'reports'} in the selected filters.</p>}
          {!analytics?.observed_heatmap.length && <p>No reports with usable coordinates match the selected filters.</p>}
        </> : <p>Shaded 0.05° forecast cells show predicted report counts, not observed reports or physical waste volume. Darker cells have higher predicted counts.</p>}
        <div className="report-table-wrap"><AppDataTable key={layer} data={mapRows} className="report-table" options={{ pageLength: 10 }}>
          <Column title="Grid area" data="key">{(key: string) => layer === 'observed'
            ? <button type="button" className="density-area-button" onClick={() => setSelectedCellKey(key)}>{key}</button>
            : <span>{key}</span>}</Column>
          <Column title={layer === 'observed' ? 'Observed reports' : 'Predicted reports'} data="count" />
        </AppDataTable></div>
      </section>

      <EmailDeliveryPanel />
      <AdminNotificationPanel />

      <section className="admin-panel report-list" id="reports">
        <header className="admin-panel__heading">
          <div>
            <h2>Review queue</h2>
            <p>{filteredReports.length} production or legacy reports shown. Date, area and source analytics filters do not apply to this queue.</p>
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
          </div>
        </header>

        <p className="report-table-hint">Swipe horizontally to view all report columns.</p>
        <div className="report-table-wrap" role="region" aria-label="Recent reports table" tabIndex={0}>
          <AppDataTable data={filteredReports} className="report-table" options={{ searching: false, pageLength: 10 }}>
            <Column title="Report" data="reference" options={{ className: 'all' }}>
              {(reference: string, _type: string, report: ReportSummary) => <span className="report-identity"><strong>{reference}</strong>
                <small>{report.reporterRole === 'user' ? 'Community User' : 'Legacy guest'}</small></span>}
            </Column>
            <Column title="Category" data="category">{(value: WasteCategory) => <span>{categoryLabels[value] ?? value}</span>}</Column>
            <Column title="Location" data="location" options={{ className: 'report-table__location' }}>{(value: string) => <span>{value}</span>}</Column>
            <Column title="Submitted" data="submittedAt">{(value: string) => <span>{value}</span>}</Column>
            <Column title="Status" data="status">{(value: ReportStatusValue) => <ReportStatus status={value} />}</Column>
            <Column title="Actions" data="id" options={{ orderable: false, searchable: false, className: 'all' }}>
              {(id: string, _type: string, report: ReportSummary) => <Link className="icon-button" to={`/admin/reports/${id}`}
                aria-label={`Open report ${report.reference}`} title="Open report"><ArrowUpRight size={17} /></Link>}
            </Column>
          </AppDataTable>
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
