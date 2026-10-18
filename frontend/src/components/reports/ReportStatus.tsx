import type { ReportStatus as ReportStatusValue } from '../../types'

const labels: Record<ReportStatusValue, string> = {
  submitted: 'Submitted',
  verified: 'Verified',
  processing: 'Processing',
  in_progress: 'In progress',
  completed: 'Completed',
  resolved: 'Resolved',
  rejected: 'Rejected',
}

interface ReportStatusProps {
  status: ReportStatusValue
}

export function ReportStatus({ status }: ReportStatusProps) {
  return (
    <span className={`status status--${status}`}>
      <span className="status__dot" aria-hidden="true" />
      {labels[status]}
    </span>
  )
}
