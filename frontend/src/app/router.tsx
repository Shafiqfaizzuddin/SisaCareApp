import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AdminLayout } from '../layouts/AdminLayout'
import { PublicLayout } from '../layouts/PublicLayout'
import { RoleGuard } from '../components/common/RoleGuard'
import { AdminDashboardPage } from '../pages/AdminDashboardPage'
import { AdminLoginPage } from '../pages/AdminLoginPage'
import { AdminReportDetailPage } from '../pages/AdminReportDetailPage'
import { EducationPage } from '../pages/EducationPage'
import { HomePage } from '../pages/HomePage'
import { LeaderboardPage } from '../pages/LeaderboardPage'
import { MemberDashboardPage } from '../pages/MemberDashboardPage'
import { ReportSuccessPage } from '../pages/ReportSuccessPage'
import { SubmitReportPage } from '../pages/SubmitReportPage'
import { UserLoginPage } from '../pages/UserLoginPage'

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'report', element: <SubmitReportPage /> },
      { path: 'report/success', element: <ReportSuccessPage /> },
      { path: 'education', element: <EducationPage /> },
      { path: 'leaderboard', element: <LeaderboardPage /> },
      {
        path: 'account',
        element: (
          <RoleGuard allow={['user']} redirectTo="/login">
            <MemberDashboardPage />
          </RoleGuard>
        ),
      },
    ],
  },
  {
    path: 'login',
    element: <UserLoginPage />,
  },
  {
    path: 'admin/login',
    element: <AdminLoginPage />,
  },
  {
    path: 'admin',
    element: (
      <RoleGuard allow={['admin']} redirectTo="/admin/login">
        <AdminLayout />
      </RoleGuard>
    ),
    children: [
      { index: true, element: <AdminDashboardPage /> },
      { path: 'reports/:reportId', element: <AdminReportDetailPage /> },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
])
