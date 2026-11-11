const STATUS_LABELS = {
  cancelled: "Cancelled",
  draft: "Draft",
  upcoming: "Upcoming",
  past: "Past",
};

function getDisplayStatus(event) {
  if (event.status === "cancelled" || event.status === "draft") return event.status;
  return event.schedule_status;
}

export function StatusBadge({ event }) {
  const status = getDisplayStatus(event);
  return <span className={`badge badge-${status}`}>{STATUS_LABELS[status]}</span>;
}

export function UrgentBadge({ event }) {
  if (!event.is_urgent) return null;
  return <span className="badge badge-urgent">Urgent</span>;
}
