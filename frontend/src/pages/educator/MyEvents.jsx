import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import CancelRegistrationDialog from "../../components/educator/CancelRegistrationDialog";
import { MapPinIcon } from "../../components/supervisor/Icons";
import { EmptyState, ErrorState, LoadingState, Notice } from "../../components/supervisor/StateViews";
import Tabs from "../../components/supervisor/Tabs";
import { useQuery } from "../../hooks/useQuery";
import { formatDate, formatTimeRange, formatTimestamp, getDateParts } from "../../lib/campusTime";
import { locationName } from "../../lib/locations";
import { useEventsApi } from "../../services/events/useEventsApi";

const STATUS = {
  upcoming: { label: "Registered", className: "badge-registered" },
  in_progress: { label: "In progress", className: "badge-upcoming" },
  past: { label: "Past registration", className: "badge-past" },
  cancelled_by_user: { label: "You cancelled", className: "badge-past" },
  event_cancelled: { label: "Event cancelled", className: "badge-cancelled" },
};

const EMPTY_TEXT = {
  upcoming: ["No upcoming registrations", "Shifts you register for will show up here."],
  past: ["No past registrations", "Shifts you were registered for appear here after they end."],
  cancelled: ["Nothing cancelled", "Registrations you cancel, or events that are cancelled, show up here."],
};

const byShiftDesc = (a, b) =>
  b.shift.shift_date.localeCompare(a.shift.shift_date) ||
  b.shift.start_time.localeCompare(a.shift.start_time);

// Splits registrations into tabs. An event the user re-registered for never shows
// as both active and user-cancelled: older cancellations move to `history`.
function groupRegistrations(list) {
  const upcoming = list.filter((r) => r.category === "upcoming" || r.category === "in_progress");
  const past = list.filter((r) => r.category === "past").sort(byShiftDesc);
  const eventCancelled = list.filter((r) => r.category === "event_cancelled");
  const userCancelled = list.filter((r) => r.category === "cancelled_by_user");

  const activeEventIds = new Set(
    [...upcoming, ...past, ...eventCancelled].map((r) => r.event.event_id),
  );
  const latestByEvent = new Map();
  for (const r of userCancelled) {
    const current = latestByEvent.get(r.event.event_id);
    if (!current || (r.cancelled_at ?? "") > (current.cancelled_at ?? "")) {
      latestByEvent.set(r.event.event_id, r);
    }
  }
  const shownCancellations = [...latestByEvent.values()].filter(
    (r) => !activeEventIds.has(r.event.event_id),
  );
  const shownIds = new Set(shownCancellations.map((r) => r.registration_id));

  return {
    upcoming,
    past,
    cancelled: [...eventCancelled, ...shownCancellations].sort(byShiftDesc),
    history: userCancelled
      .filter((r) => !shownIds.has(r.registration_id))
      .sort((a, b) => (b.cancelled_at ?? "").localeCompare(a.cancelled_at ?? "")),
  };
}

function RegistrationItem({ registration, onCancel, compact = false }) {
  const { event, shift, location } = registration;
  const status = STATUS[registration.category];
  const dateParts = getDateParts(shift.shift_date);
  const headingId = `registration-${registration.registration_id}-title`;

  return (
    <article className={`registration-item${compact ? " is-compact" : ""}`} aria-labelledby={headingId}>
      {!compact && (
        <div className="registration-date" aria-hidden="true">
          <span className="event-date-month">{dateParts.month}</span>
          <span className="event-date-day">{dateParts.day}</span>
        </div>
      )}
      <div className="registration-body">
        <div className="badges">
          <span className={`badge ${status.className}`}>{status.label}</span>
        </div>
        <h3 className="registration-title" id={headingId}>
          <Link to={`/educator/events/${event.event_id}`}>{event.title}</Link>
        </h3>
        <p className="event-meta">
          {formatDate(shift.shift_date)}, {formatTimeRange(shift.start_time, shift.end_time)}
        </p>
        <p className="event-meta explore-location">
          <MapPinIcon size={16} />
          {locationName(location)}
        </p>
        {registration.category === "cancelled_by_user" && registration.cancelled_at && (
          <p className="hint">You cancelled on {formatTimestamp(registration.cancelled_at)}.</p>
        )}
        {registration.category === "event_cancelled" && (
          <p className="hint">The organizers cancelled this event. Your registration is kept here for your records.</p>
        )}
      </div>
      <div className="registration-actions">
        <Link
          to={`/educator/events/${event.event_id}`}
          className="btn btn-secondary btn-sm"
          aria-describedby={headingId}
        >
          View details
        </Link>
        {registration.can_cancel && onCancel && (
          <button
            type="button"
            className="btn btn-danger btn-sm"
            onClick={() => onCancel(registration)}
            aria-describedby={headingId}
          >
            Cancel registration
          </button>
        )}
      </div>
    </article>
  );
}

export default function MyEvents() {
  const api = useEventsApi();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeTab = ["upcoming", "past", "cancelled"].includes(tabParam) ? tabParam : "upcoming";
  const registrationsQuery = useQuery("my-registrations", () => api.getMyRegistrations());
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelError, setCancelError] = useState("");
  const [isCancelling, setIsCancelling] = useState(false);
  const [notice, setNotice] = useState("");

  const registrations = registrationsQuery.latestData;
  const groups = registrations ? groupRegistrations(registrations) : null;

  function selectTab(tab) {
    setSearchParams(tab === "upcoming" ? {} : { tab }, { replace: true });
  }

  async function handleCancel() {
    setIsCancelling(true);
    setCancelError("");
    try {
      await api.cancelRegistration(cancelTarget.registration_id);
      setNotice(`Your registration for ${cancelTarget.event.title} was cancelled and your spot was released.`);
      setCancelTarget(null);
      registrationsQuery.reload();
    } catch (error) {
      setCancelError(error.message || "We couldn't cancel this registration. Please try again.");
    } finally {
      setIsCancelling(false);
    }
  }

  let panel;
  if (registrationsQuery.error) {
    panel = (
      <ErrorState
        title="We couldn't load your registrations"
        error={registrationsQuery.error}
        onRetry={registrationsQuery.reload}
      />
    );
  } else if (!groups) {
    panel = <LoadingState label="Loading your registrations…" />;
  } else {
    const items = groups[activeTab];
    const [emptyTitle, emptyText] = EMPTY_TEXT[activeTab];
    panel = (
      <>
        {items.length === 0 ? (
          <EmptyState
            title={emptyTitle}
            action={
              activeTab === "upcoming" && (
                <Link to="/educator/events" className="btn btn-primary">
                  Explore events
                </Link>
              )
            }
          >
            {emptyText}
          </EmptyState>
        ) : (
          <ul className={`registration-list${registrationsQuery.isLoading ? " is-refreshing" : ""}`}>
            {items.map((registration) => (
              <li key={registration.registration_id}>
                <RegistrationItem registration={registration} onCancel={setCancelTarget} />
              </li>
            ))}
          </ul>
        )}

        {activeTab === "cancelled" && groups.history.length > 0 && (
          <details className="history">
            <summary>
              Earlier cancellations ({groups.history.length})
            </summary>
            <p className="hint">
              Registrations you cancelled before registering again, or replaced with a later one.
            </p>
            <ul className="registration-list">
              {groups.history.map((registration) => (
                <li key={registration.registration_id}>
                  <RegistrationItem registration={registration} compact />
                </li>
              ))}
            </ul>
          </details>
        )}
      </>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">My events</h1>
          <p className="page-subtitle">
            Your shift registrations. Past items show what you were registered for, not attendance.
          </p>
        </div>
        <Link to="/educator/events" className="btn btn-primary">
          Explore events
        </Link>
      </div>

      <Notice onDismiss={() => setNotice("")}>{notice}</Notice>

      <section className="card">
        <Tabs
          label="My registrations"
          tabs={[
            { id: "upcoming", label: "Upcoming", count: groups?.upcoming.length },
            { id: "past", label: "Past", count: groups?.past.length },
            { id: "cancelled", label: "Cancelled", count: groups?.cancelled.length },
          ]}
          active={activeTab}
          onChange={selectTab}
        />
        <div
          className="tab-panel"
          role="tabpanel"
          id={`panel-${activeTab}`}
          aria-labelledby={`tab-${activeTab}`}
          tabIndex={0}
        >
          {panel}
        </div>
      </section>

      {cancelTarget && (
        <CancelRegistrationDialog
          eventTitle={cancelTarget.event.title}
          shift={cancelTarget.shift}
          location={cancelTarget.location}
          isBusy={isCancelling}
          error={cancelError}
          onConfirm={handleCancel}
          onCancel={() => setCancelTarget(null)}
        />
      )}
    </>
  );
}
