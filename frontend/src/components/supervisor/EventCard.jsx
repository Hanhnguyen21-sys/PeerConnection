import { Link } from "react-router-dom";
import { formatDateRange, getDateParts } from "../../lib/campusTime";
import { PencilIcon } from "./Icons";
import { StatusBadge, UrgentBadge } from "./StatusBadge";

export default function EventCard({ event }) {
  const detailPath = `/supervisor/events/${event.event_id}`;
  const headingId = `event-${event.event_id}-title`;
  const dateKey = event.next_shift_date ?? event.first_shift_date;
  const dateParts = dateKey ? getDateParts(dateKey) : null;
  const isCancelled = event.status === "cancelled";

  return (
    <article className={`event-card${isCancelled ? " is-cancelled" : ""}`} aria-labelledby={headingId}>
      <div className="event-date" aria-hidden="true">
        {dateParts ? (
          <>
            <span className="event-date-month">{dateParts.month}</span>
            <span className="event-date-day">{dateParts.day}</span>
            <span className="event-date-weekday">{dateParts.weekday}</span>
          </>
        ) : (
          <span className="event-date-weekday">No date</span>
        )}
      </div>

      <div className="event-card-body">
        <div className="badges">
          <StatusBadge event={event} />
          <UrgentBadge event={event} />
        </div>
        <h2 className="event-title" id={headingId}>
          <Link to={detailPath}>{event.title}</Link>
        </h2>
        <p className="event-meta">{formatDateRange(event.first_shift_date, event.last_shift_date)}</p>

        <dl className="event-stats">
          <div>
            <dt>Shifts</dt>
            <dd>{event.shift_count}</dd>
          </div>
          <div>
            <dt>Registered</dt>
            <dd>
              {event.active_registrations}/{event.total_capacity}
            </dd>
          </div>
          <div className={!isCancelled && event.understaffed_shifts > 0 ? "stat-warn" : undefined}>
            <dt>Understaffed</dt>
            <dd>{isCancelled ? "—" : event.understaffed_shifts}</dd>
          </div>
        </dl>

        <div className="event-actions">
          {!isCancelled && (
            <Link
              to={`${detailPath}/edit`}
              className="icon-button"
              aria-label={`Edit ${event.title}`}
              title="Edit event"
            >
              <PencilIcon size={18} />
            </Link>
          )}
          <Link to={detailPath} className="btn btn-secondary btn-sm" aria-describedby={headingId}>
            View details
          </Link>
        </div>
      </div>
    </article>
  );
}
