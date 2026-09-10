import { MotionConfig } from 'framer-motion'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppShell, FullPageLoader } from './components/AppShell'
import { EmptyState, Panel } from './components/ui'
import { useAuth } from './lib/providers'
import CitizenApp from './pages/citizen/CitizenApp'
import DataSources from './pages/citizen/DataSources'
import Login from './pages/Login'
import AlertsPage from './pages/authority/AlertsPage'
import MapPage from './pages/authority/MapPage'
import Overview from './pages/authority/Overview'
import PriorityQueuePage from './pages/authority/PriorityQueuePage'
import SimLab from './pages/authority/SimLab'
import Sitrep from './pages/authority/Sitrep'
import Telemetry from './pages/authority/Telemetry'

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

const AUTH_ROLES = ['authority', 'administrator']

export default function App() {
  const { user, loading } = useAuth()

  return (
    <MotionConfig reducedMotion="user">
      <Routes>
        <Route path="/login" element={<Login />} />

        {/* authority command centre */}
        <Route
          path="/authority"
          element={
            <RequireAuth roles={AUTH_ROLES}>
              <AppShell>
                <Overview />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route
          path="/authority/sitrep"
          element={
            <RequireAuth roles={AUTH_ROLES}>
              <AppShell>
                <Sitrep />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route
          path="/authority/predict"
          element={
            <RequireAuth roles={AUTH_ROLES}>
              <AppShell>
                <Telemetry />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route
          path="/authority/queue"
          element={
            <RequireAuth roles={AUTH_ROLES}>
              <AppShell>
                <PriorityQueuePage />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route
          path="/authority/map"
          element={
            <RequireAuth roles={AUTH_ROLES}>
              <AppShell>
                <MapPage />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route
          path="/authority/alerts"
          element={
            <RequireAuth roles={AUTH_ROLES}>
              <AppShell>
                <AlertsPage />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route
          path="/authority/lab"
          element={
            <RequireAuth roles={AUTH_ROLES}>
              <AppShell>
                <SimLab />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route
          path="/data"
          element={
            <RequireAuth>
              <AppShell>
                <DataSources />
              </AppShell>
            </RequireAuth>
          }
        />

        {/* citizen app (its own chrome: mobile column, bottom nav) */}
        <Route
          path="/citizen"
          element={
            <RequireAuth roles={['citizen']}>
              <CitizenApp initialTab="home" />
            </RequireAuth>
          }
        />
        <Route
          path="/citizen/evacuate"
          element={
            <RequireAuth roles={['citizen']}>
              <CitizenApp initialTab="evacuate" />
            </RequireAuth>
          }
        />

        <Route
          path="/"
          element={
            loading ? (
              <FullPageLoader />
            ) : (
              <Navigate to={user ? (user.role === 'citizen' ? '/citizen' : '/authority') : '/login'} replace />
            )
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </MotionConfig>
  )
}
