import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { RoleProvider } from '../features/authentication/RoleContext'
import { router } from './router'
import { ThemeProvider } from '../features/theme/ThemeProvider'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

export function AppProviders() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RoleProvider>
          <RouterProvider router={router} />
        </RoleProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
