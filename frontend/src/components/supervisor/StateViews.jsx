import { AlertIcon } from "./Icons";

export function LoadingState({ label = "Loading…" }) {
  return (
    <div className="state-view" role="status">
      <span className="spinner spinner-dark" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", error, onRetry, children }) {
  return (
    <div className="state-view state-error" role="alert">
      <AlertIcon size={28} />
      <h2 className="state-title">{title}</h2>
      {error && <p>{error.message || "Please try again."}</p>}
      {children}
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children, action }) {
  return (
    <div className="state-view">
      <h2 className="state-title">{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Notice({ children, onDismiss, tone = "success" }) {
  if (!children) return null;
  return (
    <div className={`notice notice-${tone}`} role="status">
      <span>{children}</span>
      {onDismiss && (
        <button type="button" className="btn-text" onClick={onDismiss}>
          Dismiss
        </button>
      )}
    </div>
  );
}
