import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { getAuthErrorMessage } from '../auth/authErrors'
import { BrandMark } from '../components/AuthLayout'

// Display only; the backend remains the authority on what each role can do.
const ROLE_LABELS = {
  peer_educator: 'Peer educator',
  supervisor: 'Supervisor',
}

export default function Home() {
  const { profile, profileError, isProfileLoading, reloadProfile, signOut } = useAuth()
  const [isSigningOut, setIsSigningOut] = useState(false)
  const [signOutError, setSignOutError] = useState('')

  async function handleSignOut() {
    setIsSigningOut(true)
    setSignOutError('')
    try {
      await signOut()
    } catch (error) {
      setSignOutError(getAuthErrorMessage(error))
      setIsSigningOut(false)
    }
  }

  return (
    <div className="home">
      <header className="home-header">
        <BrandMark />
        <button
          type="button"
          className="button-secondary"
          onClick={handleSignOut}
          disabled={isSigningOut}
        >
          {isSigningOut ? 'Signing out…' : 'Sign out'}
        </button>
      </header>

      <main className="home-main">
        <section className="home-card" aria-busy={isProfileLoading}>
          {isProfileLoading && (
            <p className="home-status" role="status">
              <span className="spinner spinner-dark" aria-hidden="true" />
              Loading your profile…
            </p>
          )}

          {profileError && (
            <div className="home-error" role="alert">
              <h1 className="home-title">We couldn&apos;t load your profile</h1>
              <p>{profileError.message}</p>
              <button type="button" className="button-primary" onClick={reloadProfile}>
                Try again
              </button>
            </div>
          )}

          {profile && (
            <>
              <p className="home-eyebrow">You&apos;re signed in</p>
              <h1 className="home-title">Welcome, {profile.name || profile.email}</h1>
              <dl className="home-details">
                <div>
                  <dt>Role</dt>
                  <dd>
                    <span className="role-badge">{ROLE_LABELS[profile.role] ?? profile.role}</span>
                  </dd>
                </div>
                <div>
                  <dt>Email</dt>
                  <dd>{profile.email}</dd>
                </div>
              </dl>
            </>
          )}

          <div className="form-alert" role="alert">
            {signOutError}
          </div>
        </section>
      </main>
    </div>
  )
}
