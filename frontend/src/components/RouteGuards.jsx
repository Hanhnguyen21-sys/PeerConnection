import { useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { getAuthErrorMessage } from "../auth/authErrors";
import Home from "../pages/Home";
import { BrandMark } from "./AuthLayout";

export function FullPageLoader({ label = "Loading…" }) {
  return (
    <div className="page-loader" role="status">
      <span className="spinner spinner-dark" aria-hidden="true" />
      <span className="visually-hidden">{label}</span>
    </div>
  );
}

export function RequireAuth({ children }) {
  const { session, isRestoring } = useAuth();
  const location = useLocation();

  if (isRestoring) return <FullPageLoader />;
  if (!session) return <Navigate to="/sign-in" replace state={{ from: location }} />;
  return children;
}

export function GuestOnly({ children }) {
  const { session, isRestoring } = useAuth();
  const location = useLocation();

  if (isRestoring) return <FullPageLoader />;
  if (session) {
    const from = location.state?.from;
    return <Navigate to={from ? `${from.pathname}${from.search ?? ""}` : "/"} replace />;
  }
  return children;
}

const ROLE_HOMES = {
  supervisor: "/supervisor",
  peer_educator: "/educator/events",
};

const ROLE_NAMES = {
  supervisor: "Supervisor",
  peer_educator: "Peer educator",
};

// "/" sends each role to its dashboard. Any other role (or a profile error)
// falls back to the basic signed-in screen, which can show and retry errors.
export function RootRoute() {
  const { profile, isProfileLoading } = useAuth();
  if (isProfileLoading) return <FullPageLoader label="Loading your profile…" />;
  const home = ROLE_HOMES[profile?.role];
  if (home) return <Navigate to={home} replace />;
  return <Home />;
}

function GuardMessage({ title, children, actions }) {
  return (
    <div className="guard-page">
      <header className="home-header">
        <BrandMark />
      </header>
      <main className="home-main">
        <section className="home-card" role="alert">
          <h1 className="home-title">{title}</h1>
          <div className="guard-text">{children}</div>
          <div className="guard-actions">{actions}</div>
        </section>
      </main>
    </div>
  );
}

function SignOutButton() {
  const { signOut } = useAuth();
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  async function handleClick() {
    setIsBusy(true);
    setError("");
    try {
      await signOut();
    } catch (signOutError) {
      setError(getAuthErrorMessage(signOutError));
      setIsBusy(false);
    }
  }

  return (
    <>
      <button type="button" className="btn btn-secondary" onClick={handleClick} disabled={isBusy}>
        {isBusy ? "Signing out…" : "Sign out"}
      </button>
      {error && <p className="field-error">{error}</p>}
    </>
  );
}

// Presentation-only gate: the backend must still authorize every request.
export function RequireRole({ role, children }) {
  const { profile, profileError, isProfileLoading, reloadProfile } = useAuth();

  if (isProfileLoading) return <FullPageLoader label="Checking your access…" />;

  if (profileError) {
    return (
      <GuardMessage
        title="We couldn't load your profile"
        actions={
          <>
            <button type="button" className="btn btn-primary" onClick={reloadProfile}>
              Try again
            </button>
            <SignOutButton />
          </>
        }
      >
        <p>{profileError.message}</p>
      </GuardMessage>
    );
  }

  if (profile?.role !== role) {
    // Supervisors always go back to their own dashboard.
    if (profile?.role === "supervisor") return <Navigate to={ROLE_HOMES.supervisor} replace />;
    return (
      <GuardMessage
        title={`${ROLE_NAMES[role]} access required`}
        actions={
          <>
            <Link to="/" className="btn btn-primary">
              Go to my home
            </Link>
            <SignOutButton />
          </>
        }
      >
        <p>
          This area is only available to {ROLE_NAMES[role].toLowerCase()} accounts. If you think
          this is a mistake, contact your program supervisor.
        </p>
      </GuardMessage>
    );
  }

  return children;
}
