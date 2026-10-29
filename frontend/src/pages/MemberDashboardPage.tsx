import { ArrowRight, ClipboardList } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ReportStatus } from '../components/reports/ReportStatus'
import { useRole } from '../features/authentication/useRole'
import { displayInitials } from '../lib/display-initials'

export function MemberDashboardPage() {
  const { user, memberReports, isMemberDataLoading, memberDataError, refreshMemberData } = useRole()
  if (!user) return null

  return <section className="section member-page"><div className="container">
    <header className="member-hero"><div className="member-hero__identity">
      <span className="member-hero__avatar">{displayInitials(user.name)}</span>
      <div><p className="eyebrow">Community account</p><h1>{user.name}</h1></div>
    </div><Link className="button button--primary" to="/report">Submit a new report <ArrowRight size={17} /></Link></header>
    <section className="member-panel"><header><div><h2>Your recent reports</h2>
      <p>Follow municipal review and response updates here.</p></div><ClipboardList size={20} /></header>
      <div className="member-report-list">
        {isMemberDataLoading ? <p className="empty-state">Loading your reports...</p>
          : memberDataError ? <div className="empty-state" role="alert"><p>{memberDataError}</p>
            <button className="button button--secondary" type="button" onClick={refreshMemberData}>Try again</button></div>
          : memberReports.length ? memberReports.map(report => <div key={report.id}><div>
            <Link to={`/account/reports/${encodeURIComponent(report.id)}`}>{report.reference}</Link><span>{report.location}</span></div>
            <ReportStatus status={report.status} /></div>)
          : <p className="empty-state">No reports submitted yet.</p>}
      </div>
    </section>
  </div></section>
}
