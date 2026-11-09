import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AdminLayout } from '../layouts/AdminLayout'
import { PublicLayout } from '../layouts/PublicLayout'
import { RoleGuard } from '../components/common/RoleGuard'
import { AdminDashboardPage } from '../pages/AdminDashboardPage'
import { AdminLoginPage } from '../pages/AdminLoginPage'
import { AdminReportDetailPage } from '../pages/AdminReportDetailPage'
import { AdminRecyclingPointsPage } from '../pages/AdminRecyclingPointsPage'
import { AdminLearnPage } from '../pages/AdminLearnPage'
import { EducationPage } from '../pages/EducationPage'
import { HomePage } from '../pages/HomePage'
import { MemberDashboardPage } from '../pages/MemberDashboardPage'
import { MemberReportDetailPage } from '../pages/MemberReportDetailPage'
import { ReportSuccessPage } from '../pages/ReportSuccessPage'
import { SubmitReportPage } from '../pages/SubmitReportPage'
import { UserLoginPage } from '../pages/UserLoginPage'
import { UserSignupPage } from '../pages/UserSignupPage'
import { PasswordResetPage } from '../pages/PasswordResetPage'
import { PrivacyPage } from '../pages/PrivacyPage'
import { StaffLoginPage } from '../pages/StaffLoginPage'
import { StaffLayout } from '../layouts/StaffLayout'
import { StaffDashboardPage } from '../pages/StaffDashboardPage'
import { StaffTaskDetailPage } from '../pages/StaffTaskDetailPage'
import { AdminStaffPage } from '../pages/AdminStaffPage'
import { StaffAcceptInvitePage } from '../pages/StaffAcceptInvitePage'

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'report', element: <RoleGuard allow={['user']} redirectTo="/login"><SubmitReportPage /></RoleGuard> },
      { path: 'report/success', element: <ReportSuccessPage /> },
      { path: 'education', element: <EducationPage /> },
      { path: 'privacy', element: <PrivacyPage /> },
      {
        path: 'account',
        element: (
          <RoleGuard allow={['user']} redirectTo="/login">
            <MemberDashboardPage />
          </RoleGuard>
        ),
      },
      { path: 'account/reports/:reportId', element: <RoleGuard allow={['user']} redirectTo="/login"><MemberReportDetailPage /></RoleGuard> },
    ],
  },
  {
    path: 'login',
    element: <UserLoginPage />,
  },
  {
    path: 'signup',
    element: <UserSignupPage />,
  },
  { path: 'password-reset', element: <PasswordResetPage /> },
  { path: 'staff/login', element: <StaffLoginPage /> },
  { path: 'staff/accept-invite', element: <StaffAcceptInvitePage /> },
  { path: 'staff', element: <RoleGuard allow={['staff']} redirectTo="/staff/login"><StaffLayout /></RoleGuard>,
    children: [{ index: true, element: <StaffDashboardPage /> }, { path: 'tasks/:reportId', element: <StaffTaskDetailPage /> }] },
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
      { path: 'recycling-points', element: <AdminRecyclingPointsPage /> },
      { path: 'learn', element: <AdminLearnPage /> },
      { path: 'staff', element: <AdminStaffPage /> },
      { path: 'reports/:reportId', element: <AdminReportDetailPage /> },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
])
