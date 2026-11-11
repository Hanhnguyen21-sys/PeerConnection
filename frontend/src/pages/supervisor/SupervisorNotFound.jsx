import { Link } from "react-router-dom";
import { EmptyState } from "../../components/supervisor/StateViews";

export default function SupervisorNotFound() {
  return (
    <EmptyState
      title="Page not found"
      action={
        <Link to="/supervisor" className="btn btn-secondary">
          Back to all events
        </Link>
      }
    >
      This page doesn&apos;t exist in the supervisor dashboard.
    </EmptyState>
  );
}
