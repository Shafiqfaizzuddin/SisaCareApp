import DataTable, { Column } from 'datatables.net-react'
import DataTablesCore, { type Config } from 'datatables.net-dt'
import 'datatables.net-responsive-dt'
import 'datatables.net-dt/css'
import 'datatables.net-responsive-dt/css'
import './app-data-table.css'
import type { ReactNode } from 'react'

const registerDataTablesCore = DataTable.use
registerDataTablesCore(DataTablesCore)

interface AppDataTableProps<T extends object> {
  data: T[]
  children: ReactNode
  className?: string
  options?: Config
}

export function AppDataTable<T extends object>({ data, children, className = '', options }: AppDataTableProps<T>) {
  return <DataTable data={data} className={`display ${className}`.trim()}
    options={{ responsive: true, autoWidth: false, pageLength: 10, order: [], ...options }}>
    {children}
  </DataTable>
}

export { Column }
