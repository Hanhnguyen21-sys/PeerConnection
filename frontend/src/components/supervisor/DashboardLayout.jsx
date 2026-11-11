import { useState } from "react";
import { Link, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import logo from "../../assets/logo.jpg";
import { useAuth } from "../../auth/AuthContext";
import { getAuthErrorMessage } from "../../auth/authErrors";
import { LogOutIcon, SearchIcon } from "./Icons";
import "./supervisor.css";

function initials(name = "") {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts.at(-1)[0] : "");
}

function TopSearch({ searchPath }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState("");
  const onHome = pathname === searchPath;
  const value = onHome ? (searchParams.get("q") ?? "") : draft;

  function handleChange(event) {
    const next = event.target.value;
    if (!onHome) {
      setDraft(next);
      return;
    }
    setSearchParams(
      (params) => {
        if (next) params.set("q", next);
        else params.delete("q");
        return params;
      },
      { replace: true },
    );
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (onHome) return;
    const term = draft.trim();
    setDraft("");
    navigate(term ? `${searchPath}?q=${encodeURIComponent(term)}` : searchPath);
  }

  return (
    <form className="sv-search" role="search" onSubmit={handleSubmit}>
      <label htmlFor="sv-search-input" className="visually-hidden">
        Search events by title
      </label>
      <SearchIcon size={18} />
      <input
        id="sv-search-input"
        type="search"
        placeholder="Search events…"
        value={value}
        onChange={handleChange}
        autoComplete="off"
      />
    </form>
  );
}

function UserMenu({ roleLabel }) {
  const { profile, signOut } = useAuth();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [error, setError] = useState("");

  async function handleSignOut() {
    setIsSigningOut(true);
    setError("");
    try {
      await signOut();
    } catch (signOutError) {
      setError(getAuthErrorMessage(signOutError));
      setIsSigningOut(false);
    }
  }

  return (
    <div className="sv-user">
      <div className="sv-user-text">
        <span className="sv-user-name">{profile.name || profile.email}</span>
        <span className="sv-user-role">{roleLabel}</span>
      </div>
      <span className="avatar" aria-hidden="true">
        {initials(profile.name || profile.email).toUpperCase()}
      </span>
      <button
        type="button"
        className="btn btn-secondary btn-sm sv-signout"
        onClick={handleSignOut}
        disabled={isSigningOut}
        aria-label={isSigningOut ? "Signing out" : "Sign out"}
      >
        <LogOutIcon size={18} />
        <span className="sv-signout-label">{isSigningOut ? "Signing out…" : "Sign out"}</span>
      </button>
      {error && (
        <p className="sv-user-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

// Shared shell for the role dashboards: sidebar, event search, and profile.
// navItems: [{ to, label, Icon, isActive?(pathname) }]
export default function DashboardLayout({ homePath, searchPath, navItems, navLabel, roleLabel }) {
  const { pathname } = useLocation();

  return (
    <div className="sv">
      <a className="skip-link" href="#sv-main">
        Skip to main content
      </a>

      <nav className="sv-sidebar" aria-label={navLabel}>
        <Link to={homePath} className="sv-logo" aria-label="Peer Connections home">
          <img src={logo} alt="" width="44" height="44" />
        </Link>
        <ul className="sv-nav">
          {navItems.map(({ to, label, Icon, isActive }) => {
            const active = isActive ? isActive(pathname) : pathname === to;
            return (
              <li key={to}>
                <Link to={to} className="sv-nav-link" aria-current={active ? "page" : undefined}>
                  <Icon size={22} />
                  <span>{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="sv-main-col">
        <header className="sv-topbar">
          <Link to={homePath} className="sv-topbar-logo" aria-label="Peer Connections home">
            <img src={logo} alt="" width="36" height="36" />
          </Link>
          <TopSearch searchPath={searchPath} />
          <div className="sv-topbar-end">
            <UserMenu roleLabel={roleLabel} />
          </div>
        </header>
        <main id="sv-main" className="sv-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
