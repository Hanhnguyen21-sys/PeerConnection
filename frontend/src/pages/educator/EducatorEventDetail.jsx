import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import CancelRegistrationDialog from "../../components/educator/CancelRegistrationDialog";
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  ExternalLinkIcon,
  MapPinIcon,
} from "../../components/supervisor/Icons";
import { EmptyState, ErrorState, LoadingState, Notice } from "../../components/supervisor/StateViews";
import { UrgentBadge } from "../../components/supervisor/StatusBadge";
import { useQuery } from "../../hooks/useQuery";
import { CAMPUS_TIME_LABEL, formatDate, formatDateRange, formatTimeRange, formatTimestamp } from "../../lib/campusTime";
import { locationName } from "../../lib/locations";
import { safeExternalUrl } from "../../lib/validation";
import { isNotFoundError } from "../../services/errors";
import { useEventsApi } from "../../services/events/useEventsApi";

function EventStatusBadge({ event }) {
  if (event.status === "cancelled") return <span className="badge badge-cancelled">Event cancelled</span>;
  if (event.schedule_status === "past") return <span className="badge badge-past">Past</span>;
  return <span className="badge badge-upcoming">Upcoming</span>;
}

function ShiftAction({ shift, isPending, isBusy, onRegister, onCancel }) {
  const { eligibility } = shift;
  const hintId = `shift-${shift.shift_id}-action-hint`;

  switch (eligibility.code) {
    case "open":
      return (
        <button type="button" className="btn btn-primary" onClick={onRegister} disabled={isBusy}>
          {isPending && <span className="spinner" aria-hidden="true" />}
          {isPending ? "Registering…" : "Register"}
        </button>
      );
    case "registered":
      return (
        <div className="shift-action-stack">
          <span className="badge badge-registered">
            <CheckCircleIcon size={14} />
            {shift.has_ended ? "Past registration" : shift.has_started ? "In progress" : "Registered"}
          </span>
          {!shift.has_started && (
            <button type="button" className="btn btn-danger btn-sm" onClick={onCancel} disabled={isBusy}>
              Cancel registration
            </button>
          )}
        </div>
      );
    case "full":
      return (
        <button type="button" className="btn btn-secondary" disabled>
          Full
        </button>
      );
    case "registered_other_shift":
      return (
        <button type="button" className="btn btn-secondary" disabled>
          Already registered for this event
        </button>
      );
    case "conflict": {
      const c = eligibility.conflict;
      return (
        <div className="shift-action-stack">
          <button type="button" className="btn btn-secondary" disabled aria-describedby={hintId}>
            Schedule conflict
          </button>
          <p className="hint" id={hintId}>
            Overlaps your shift for{" "}
            <Link className="text-link" to={`/educator/events/${c.event_id}`}>
              {c.title}
            </Link>
            , {formatDate(c.shift_date)}, {formatTimeRange(c.start_time, c.end_time)}.
          </p>
        </div>
      );
    }
    case "event_cancelled":
      return (
        <button type="button" className="btn btn-secondary" disabled>
          Event cancelled
        </button>
      );
    default:
      return (
        <div className="shift-action-stack">
          <button type="button" className="btn btn-secondary" disabled aria-describedby={hintId}>
            Registration closed
          </button>
          <p className="hint" id={hintId}>
            {shift.has_ended ? "This shift has ended." : "This shift has already started."}
          </p>
        </div>
      );
  }
}

export default function EducatorEventDetail() {
  const { eventId } = useParams();
  const api = useEventsApi();
  const eventQuery = useQuery(`educator-event:${eventId}`, () => api.getEducatorEvent(eventId));
  const [pendingShiftId, setPendingShiftId] = useState(null);
  const [shiftError, setShiftError] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  const [notice, setNotice] = useState("");
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelError, setCancelError] = useState("");
  const [isCancelling, setIsCancelling] = useState(false);
  const pendingRef = useRef(false);
  const confirmationRef = useRef(null);

  useEffect(() => {
    if (confirmation) confirmationRef.current?.focus();
  }, [confirmation]);

  const event =
    eventQuery.latestData && String(eventQuery.latestData.event_id) === eventId
      ? eventQuery.latestData
      : eventQuery.data;

  if (isNotFoundError(eventQuery.error)) {
    return (
      <EmptyState
        title="Event not found"
        action={
          <Link to="/educator/events" className="btn btn-secondary">
            Back to events
          </Link>
        }
      >
        This event doesn&apos;t exist or isn&apos;t open to peer educators.
      </EmptyState>
    );
  }
  if (eventQuery.error) {
    return <ErrorState title="We couldn't load this event" error={eventQuery.error} onRetry={eventQuery.reload} />;
  }
  if (!event) return <LoadingState label="Loading event…" />;

  const isCancelled = event.status === "cancelled";
  // Stay busy until the refreshed event arrives so buttons never act on stale availability.
  const isBusy = pendingShiftId !== null || isCancelling || eventQuery.isLoading;

  async function handleRegister(shift) {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPendingShiftId(shift.shift_id);
    setShiftError(null);
    setConfirmation(null);
    setNotice("");
    try {
      const registration = await api.registerForShift(shift.shift_id);
      setConfirmation(registration);
    } catch (error) {
      setShiftError({
        shiftId: shift.shift_id,
        message: error.message || "We couldn't register you for this shift. Please try again.",
      });
    } finally {
      pendingRef.current = false;
      setPendingShiftId(null);
      eventQuery.reload();
    }
  }

  async function handleCancelRegistration() {
    setIsCancelling(true);
    setCancelError("");
    try {
      await api.cancelRegistration(cancelTarget.eligibility.registration_id);
      setCancelTarget(null);
      setConfirmation(null);
      setNotice("Your registration was cancelled and your spot was released.");
      eventQuery.reload();
    } catch (error) {
      setCancelError(error.message || "We couldn't cancel this registration. Please try again.");
    } finally {
      setIsCancelling(false);
    }
  }

  return (
    <>
      <Link to="/educator/events" className="back-link">
        <ArrowLeftIcon size={16} />
        Explore events
      </Link>

      {confirmation && (
        <div className="confirmation" role="status" tabIndex={-1} ref={confirmationRef}>
          <CheckCircleIcon size={24} />
          <div>
            <p className="confirmation-title">You&apos;re registered for {confirmation.event.title}</p>
            <p>
              {formatDate(confirmation.shift.shift_date)},{" "}
              {formatTimeRange(confirmation.shift.start_time, confirmation.shift.end_time)} ·{" "}
              {locationName(confirmation.location)}
            </p>
            <Link to="/educator/my-events" className="text-link">
              View My Events
            </Link>
          </div>
        </div>
      )}

      <Notice onDismiss={() => setNotice("")}>{notice}</Notice>

      {isCancelled && (
        <div className="callout callout-danger">
          This event was cancelled
          {event.cancelled_at ? ` on ${formatTimestamp(event.cancelled_at)}` : ""} by the organizers.
          Registration is closed.
          {event.my_registration && " Your registration is kept in My Events under Cancelled."}
        </div>
      )}

      <section className="card detail-header" aria-labelledby="event-heading">
        <div className="detail-header-main">
          <div className="badges">
            <EventStatusBadge event={event} />
            <UrgentBadge event={event} />
            {event.my_registration && !isCancelled && (
              <span className="badge badge-registered">
                <CheckCircleIcon size={14} />
                Registered
              </span>
            )}
          </div>
          <h1 className="page-title" id="event-heading">
            {event.title}
          </h1>
          <p className="event-meta">{formatDateRange(event.first_shift_date, event.last_shift_date)}</p>
          {event.description && <p className="detail-description">{event.description}</p>}
        </div>
      </section>

      <section className="card" aria-labelledby="shifts-heading">
        <div className="section-heading-row">
          <div>
            <h2 className="section-title" id="shifts-heading">
              Shifts
            </h2>
            <p className="hint">
              Times are campus time ({CAMPUS_TIME_LABEL}). You can register for one shift per event.
            </p>
          </div>
        </div>

        {event.shifts.length === 0 ? (
          <EmptyState title="No shifts">This event has no shifts yet.</EmptyState>
        ) : (
          <ul className="shift-list educator-shift-list">
            {event.shifts.map((shift) => {
              const mapUrl = safeExternalUrl(shift.location?.map_url);
              const full = shift.remaining_spots === 0;
              const percent = shift.capacity
                ? Math.min((shift.active_registrations / shift.capacity) * 100, 100)
                : 0;
              const isMine = shift.eligibility.code === "registered";
              return (
                <li key={shift.shift_id} className={`shift-item${isMine ? " is-mine" : ""}`}>
                  <div>
                    <p className="shift-date">{formatDate(shift.shift_date)}</p>
                    <p className="shift-time">{formatTimeRange(shift.start_time, shift.end_time)}</p>
                  </div>
                  <div className="shift-location">
                    <MapPinIcon size={18} />
                    <div>
                      <p className="shift-location-name">{locationName(shift.location)}</p>
                      {shift.location?.directions && <p className="hint">{shift.location.directions}</p>}
                      {mapUrl && (
                        <a className="text-link" href={mapUrl} target="_blank" rel="noopener noreferrer">
                          Open map
                          <ExternalLinkIcon size={14} />
                          <span className="visually-hidden"> (opens in a new tab)</span>
                        </a>
                      )}
                    </div>
                  </div>
                  <div className="shift-capacity">
                    <p>
                      <strong>
                        {shift.active_registrations}/{shift.capacity}
                      </strong>{" "}
                      registered · {full ? "no spots left" : `${shift.remaining_spots} spot${shift.remaining_spots === 1 ? "" : "s"} left`}
                    </p>
                    <div className="meter" aria-hidden="true">
                      <span style={{ width: `${percent}%` }} />
                    </div>
                  </div>
                  <div className="shift-action">
                    <ShiftAction
                      shift={shift}
                      isPending={pendingShiftId === shift.shift_id}
                      isBusy={isBusy}
                      onRegister={() => handleRegister(shift)}
                      onCancel={() => {
                        setCancelError("");
                        setCancelTarget(shift);
                      }}
                    />
                    {shiftError?.shiftId === shift.shift_id && (
                      <p className="error-text" role="alert">
                        {shiftError.message}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {cancelTarget && (
        <CancelRegistrationDialog
          eventTitle={event.title}
          shift={cancelTarget}
          location={cancelTarget.location}
          isBusy={isCancelling}
          error={cancelError}
          onConfirm={handleCancelRegistration}
          onCancel={() => setCancelTarget(null)}
        />
      )}
    </>
  );
}
