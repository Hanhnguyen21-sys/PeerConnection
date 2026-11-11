import { Link } from "react-router-dom";
import { formatDate, formatDateRange, formatTimeRange, getDateParts } from "../../lib/campusTime";
import { CheckCircleIcon, MapPinIcon } from "../supervisor/Icons";
import { UrgentBadge } from "../supervisor/StatusBadge";

function spotsLabel(event) {
  if (event.remaining_spots === 0) return "Full";
  return `${event.remaining_spots} spot${event.remaining_spots === 1 ? "" : "s"} left`;
}

export default function EducatorEventCard({ event }) {
  const detailPath = `/educator/events/${event.event_id}`;
  const headingId = `explore-${event.event_id}-title`;
  const dateParts = getDateParts(event.next_shift_date);
  const isFull = event.remaining_spots === 0;

  return (
    <article className="event-card explore-card" aria-labelledby={headingId}>
      <div className="explore-visual" aria-hidden="true">
        <div className="explore-visual-date">
          <span className="event-date-month">{dateParts.month}</span>
          <span className="event-date-day">{dateParts.day}</span>
          <span className="event-date-weekday">{dateParts.weekday}</span>
        </div>
        <span className={`explore-visual-strip${isFull ? " is-full" : ""}`}>{spotsLabel(event)}</span>
      </div>

      <div className="event-card-body">
        <div className="badges">
          {event.my_registration && (
            <span className="badge badge-registered">
              <CheckCircleIcon size={14} />
              Registered
            </span>
          )}
          <UrgentBadge event={event} />
        </div>
        <h2 className="event-title" id={headingId}>
          <Link to={detailPath}>{event.title}</Link>
        </h2>
        {event.description && <p className="explore-description">{event.description}</p>}
        <p className="event-meta">{formatDateRange(event.next_shift_date, event.last_shift_date)}</p>
        {event.location_summary && (
          <p className="event-meta explore-location">
            <MapPinIcon size={16} />
            {event.location_summary}
          </p>
        )}
        {event.my_registration && (
          <p className="explore-mine">
            Your shift: {formatDate(event.my_registration.shift_date)},{" "}
            {formatTimeRange(event.my_registration.start_time, event.my_registration.end_time)}
          </p>
        )}

        <div className="explore-footer">
          <span className={`spots-pill${isFull ? " is-full" : ""}`}>
            {event.open_shift_count} open shift{event.open_shift_count === 1 ? "" : "s"} ·{" "}
            {spotsLabel(event)}
          </span>
          <Link to={detailPath} className="btn btn-secondary btn-sm" aria-describedby={headingId}>
            View details
          </Link>
        </div>
      </div>
    </article>
  );
}
