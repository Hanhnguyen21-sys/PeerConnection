import { Link } from "react-router-dom";
import { EmptyState } from "../../components/supervisor/StateViews";

export default function EducatorNotFound() {
  return (
    <EmptyState
      title="Page not found"
      action={
        <Link to="/educator/events" className="btn btn-secondary">
          Explore events
        </Link>
      }
    >
      This page doesn&apos;t exist.
    </EmptyState>
  );
}
