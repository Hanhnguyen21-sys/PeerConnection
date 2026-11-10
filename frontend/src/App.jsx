import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import Home from './pages/Home'
import SignIn from './pages/SignIn'
import SignUp from './pages/SignUp'
import './App.css'

function FullPageLoader() {
  return (
    <div className="page-loader" role="status">
      <span className="spinner spinner-dark" aria-hidden="true" />
      <span className="visually-hidden">Loading…</span>
    </div>
  )
}

function RequireAuth({ children }) {
  const { session, isRestoring } = useAuth()
  const location = useLocation()

  if (isRestoring) return <FullPageLoader />
  if (!session) return <Navigate to="/sign-in" replace state={{ from: location }} />
  return children
}

function GuestOnly({ children }) {
  const { session, isRestoring } = useAuth()
  const location = useLocation()

  if (isRestoring) return <FullPageLoader />
  if (session) return <Navigate to={location.state?.from?.pathname ?? '/'} replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <RequireAuth>
            <Home />
          </RequireAuth>
        }
      />
      <Route
        path="/sign-in"
        element={
          <GuestOnly>
            <SignIn />
          </GuestOnly>
        }
      />
      <Route
        path="/sign-up"
        element={
          <GuestOnly>
            <SignUp />
          </GuestOnly>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
