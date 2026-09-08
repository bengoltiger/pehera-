import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppShell, FullPageLoader } from './components/AppShell'
import { EmptyState, Panel } from './components/ui'
import { useAuth } from './lib/providers'
import Login from './pages/Login'
import Overview from './pages/authority/Overview'
import PriorityQueuePage from './pages/authority/PriorityQueuePage'
import AlertsPage from './pages/authority/AlertsPage'
import SimLab from './pages/authority/SimLab'
import MapPage from './pages/authority/MapPage'

function RequireAuth({ children, roles }: { children: React.ReactNode; roles?: string[] }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <FullPageLoader />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (roles && !roles.includes(user.role)) {
    return (
      <AppShell>
        <div className="p-4">
          <Panel title="Access denied">
            <EmptyState
              title="Your role cannot open this screen"
              detail={`This area requires one of: ${roles.join(', ')}. You are signed in as ${user.role}. Access control is enforced by the server, not by hiding buttons.`}
            />
          </Panel>
        </div>
      </AppShell>
    )
  }
  return <>{children}</>
}

export default function App() {
  const { user, loading } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        path="/authority"
        element={
          <RequireAuth roles={['authority', 'administrator']}>
            <AppShell>
              <Overview />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/authority/queue"
        element={
          <RequireAuth roles={['authority', 'administrator']}>
            <AppShell>
              <PriorityQueuePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/authority/map"
        element={
          <RequireAuth roles={['authority', 'administrator']}>
            <AppShell>
              <MapPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/authority/alerts"
        element={
          <RequireAuth roles={['authority', 'administrator']}>
            <AppShell>
              <AlertsPage />
            </AppShell>
          </RequireAuth>
        }
      />

      <Route
        path="/authority/lab"
        element={
          <RequireAuth roles={['authority', 'administrator']}>
            <AppShell>
              <SimLab />
            </AppShell>
          </RequireAuth>
        }
      />

      <Route
        path="/"
        element={
          loading ? (
            <FullPageLoader />
          ) : (
            <Navigate to={user ? (user.role === 'citizen' ? '/login' : '/authority') : '/login'} replace />
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
