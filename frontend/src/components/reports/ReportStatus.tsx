import type { ReportStatus as ReportStatusValue } from '../../types'

const labels: Record<ReportStatusValue, string> = {
  processing: 'Processing',
  in_progress: 'In progress',
  completed: 'Completed',
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
