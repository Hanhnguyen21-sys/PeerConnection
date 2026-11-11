import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ConfirmDialog } from "../../components/Modal";
import {
  ArrowLeftIcon,
  BanIcon,
  ExternalLinkIcon,
  MapPinIcon,
  PencilIcon,
  TrashIcon,
} from "../../components/supervisor/Icons";
import { EmptyState, ErrorState, LoadingState, Notice } from "../../components/supervisor/StateViews";
import { StatusBadge, UrgentBadge } from "../../components/supervisor/StatusBadge";
import Tabs from "../../components/supervisor/Tabs";
import { useQuery } from "../../hooks/useQuery";
import { formatDate, formatDateRange, formatTimeRange, formatTimestamp } from "../../lib/campusTime";
import { safeExternalUrl } from "../../lib/validation";
import { isNotFoundError } from "../../services/errors";
import { useEventsApi } from "../../services/events/useEventsApi";

function shiftLabel(shift) {
  return `${formatDate(shift.shift_date)}, ${formatTimeRange(shift.start_time, shift.end_time)}`;
}

function ShiftList({ shifts }) {
  if (shifts.length === 0) {
    return <EmptyState title="No shifts">This event has no shifts yet.</EmptyState>;
  }
  return (
    <ul className="shift-list">
      {shifts.map((shift) => {
        const mapUrl = safeExternalUrl(shift.location?.map_url);
        const full = shift.active_registrations >= shift.capacity;
        const percent = shift.capacity ? Math.min((shift.active_registrations / shift.capacity) * 100, 100) : 0;
        return (
          <li key={shift.shift_id} className="shift-item">
            <div>
              <p className="shift-date">{formatDate(shift.shift_date)}</p>
              <p className="shift-time">{formatTimeRange(shift.start_time, shift.end_time)}</p>
            </div>
            <div className="shift-location">
              <MapPinIcon size={18} />
              <div>
                {shift.location ? (
                  <>
                    <p className="shift-location-name">
                      {shift.location.building} · {shift.location.room_or_area}
                    </p>
                    {shift.location.directions && <p className="hint">{shift.location.directions}</p>}
                    {mapUrl && (
                      <a className="text-link" href={mapUrl} target="_blank" rel="noopener noreferrer">
                        Open map
                        <ExternalLinkIcon size={14} />
                        <span className="visually-hidden"> (opens in a new tab)</span>
                      </a>
                    )}
                  </>
                ) : (
                  <p className="hint">Location unavailable</p>
                )}
              </div>
            </div>
            <div className="shift-capacity">
              <p>
                <strong>
                  {shift.active_registrations}/{shift.capacity}
                </strong>{" "}
                registered
              </p>
              <div className="meter" aria-hidden="true">
                <span style={{ width: `${percent}%` }} />
              </div>
              <span className={`badge ${full ? "badge-full" : "badge-understaffed"}`}>
                {full ? "Full" : `${shift.remaining_spots} spot${shift.remaining_spots === 1 ? "" : "s"} left`}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function ParticipantList({ participants, shifts }) {
  const [shiftFilter, setShiftFilter] = useState("all");
  const visible =
    shiftFilter === "all"
      ? participants
      : participants.filter((p) => String(p.shift.shift_id) === shiftFilter);

  return (
    <>
      <div className="participant-toolbar">
        <div className="form-field">
          <label className="label" htmlFor="participant-shift-filter">
            Shift
          </label>
          <select
            id="participant-shift-filter"
            className="select"
            value={shiftFilter}
            onChange={(event) => setShiftFilter(event.target.value)}
          >
            <option value="all">All shifts</option>
            {shifts.map((shift) => (
              <option key={shift.shift_id} value={String(shift.shift_id)}>
                {shiftLabel(shift)}
              </option>
            ))}
          </select>
        </div>
        <p className="hint" role="status">
          {visible.length} active registration{visible.length === 1 ? "" : "s"}
        </p>
      </div>

      {visible.length === 0 ? (
        <EmptyState title="No active registrations">
          {shiftFilter === "all"
            ? "No peer educators are registered for this event yet."
            : "No peer educators are registered for this shift yet."}
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">Peer educators with active registrations</caption>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Email</th>
                <th scope="col">Registered shift</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((participant) => (
                <tr key={participant.registration_id}>
                  <td>{participant.user.name}</td>
                  <td>
                    <a className="text-link" href={`mailto:${participant.user.email}`}>
                      {participant.user.email}
                    </a>
                  </td>
                  <td>{shiftLabel(participant.shift)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export default function EventDetail() {
  const { eventId } = useParams();
  const api = useEventsApi();
  const navigate = useNavigate();
  const location = useLocation();
  const [notice, setNotice] = useState(location.state?.notice ?? "");
  const [activeTab, setActiveTab] = useState("shifts");
  const [dialog, setDialog] = useState(null);
  const [dialogError, setDialogError] = useState("");
  const [isWorking, setIsWorking] = useState(false);

  const eventQuery = useQuery(`event:${eventId}`, () => api.getEvent(eventId));
  const participantsQuery = useQuery(`participants:${eventId}`, () => api.getParticipants(eventId));

  // Keep showing this event while it refreshes after an action.
  const event =
    eventQuery.latestData && String(eventQuery.latestData.event_id) === eventId
      ? eventQuery.latestData
      : eventQuery.data;

  if (isNotFoundError(eventQuery.error)) {
    return (
      <EmptyState
        title="Event not found"
        action={
          <Link to="/supervisor" className="btn btn-secondary">
            Back to all events
          </Link>
        }
      >
        This event doesn&apos;t exist or may have been deleted.
      </EmptyState>
    );
  }
  if (eventQuery.error) {
    return <ErrorState title="We couldn't load this event" error={eventQuery.error} onRetry={eventQuery.reload} />;
  }
  if (!event) return <LoadingState label="Loading event…" />;

  const isCancelled = event.status === "cancelled";
  const isPast = event.schedule_status === "past";
  const canDelete = event.status === "draft" && !event.has_registration_history;
  const openSpots = event.shifts.reduce((sum, shift) => sum + shift.remaining_spots, 0);

  function openDialog(type) {
    setDialogError("");
    setDialog(type);
  }

  async function handleCancelEvent() {
    setIsWorking(true);
    setDialogError("");
    try {
      await api.cancelEvent(event.event_id);
      setDialog(null);
      setNotice("Event cancelled. Registration is closed, and existing registrations are kept as history.");
      eventQuery.reload();
      participantsQuery.reload();
    } catch (error) {
      setDialogError(error.message || "We couldn't cancel this event. Please try again.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleDelete() {
    setIsWorking(true);
    setDialogError("");
    try {
      await api.deleteDraftEvent(event.event_id);
      navigate("/supervisor", { replace: true, state: { notice: `“${event.title}” was deleted.` } });
    } catch (error) {
      setDialogError(error.message || "We couldn't delete this draft. Please try again.");
      setIsWorking(false);
    }
  }

  return (
    <>
      <Link to="/supervisor" className="back-link">
        <ArrowLeftIcon size={16} />
        All events
      </Link>

      <Notice onDismiss={() => setNotice("")}>{notice}</Notice>

      {isCancelled && (
        <div className="callout callout-danger">
          This event was cancelled
          {event.cancelled_at ? ` on ${formatTimestamp(event.cancelled_at)}` : ""}. Registration is
          closed, and the shifts and registrations below are kept as history.
        </div>
      )}

      <section className="card detail-header" aria-labelledby="event-heading">
        <div className="detail-header-main">
          <div className="badges">
            <StatusBadge event={event} />
            <UrgentBadge event={event} />
          </div>
          <h1 className="page-title" id="event-heading">
            {event.title}
          </h1>
          <p className="event-meta">
            {formatDateRange(event.first_shift_date, event.last_shift_date)}
            {event.organizer && ` · Organized by ${event.organizer.name}`}
          </p>
          {event.description && <p className="detail-description">{event.description}</p>}
        </div>

        <div className="detail-actions">
          {!isCancelled && (
            <Link to={`/supervisor/events/${event.event_id}/edit`} className="btn btn-secondary">
              <PencilIcon size={16} />
              Edit
            </Link>
          )}
          {!isCancelled && !isPast && (
            <button type="button" className="btn btn-danger" onClick={() => openDialog("cancel")}>
              <BanIcon size={16} />
              Cancel event
            </button>
          )}
          {canDelete && (
            <button type="button" className="btn btn-danger" onClick={() => openDialog("delete")}>
              <TrashIcon size={16} />
              Delete draft
            </button>
          )}
        </div>
      </section>

      <dl className="stat-grid">
        <div className="stat-card">
          <dt>Shifts</dt>
          <dd>{event.shift_count}</dd>
        </div>
        <div className="stat-card">
          <dt>Active registrations</dt>
          <dd>
            {event.active_registrations}/{event.total_capacity}
          </dd>
        </div>
        <div className="stat-card">
          <dt>Open spots</dt>
          <dd>{isCancelled ? "—" : openSpots}</dd>
        </div>
        <div className={`stat-card${!isCancelled && event.understaffed_shifts ? " stat-warn" : ""}`}>
          <dt>Understaffed shifts</dt>
          <dd>{isCancelled ? "—" : event.understaffed_shifts}</dd>
        </div>
      </dl>

      <section className="card">
        <Tabs
          label="Event information"
          tabs={[
            { id: "shifts", label: "Shifts", count: event.shifts.length },
            {
              id: "participants",
              label: "Participants",
              count: participantsQuery.latestData?.length ?? "…",
            },
          ]}
          active={activeTab}
          onChange={setActiveTab}
        />
        <div
          className="tab-panel"
          role="tabpanel"
          id={`panel-${activeTab}`}
          aria-labelledby={`tab-${activeTab}`}
          tabIndex={0}
        >
          {activeTab === "shifts" && <ShiftList shifts={event.shifts} />}
          {activeTab === "participants" &&
            (participantsQuery.error ? (
              <ErrorState
                title="We couldn't load participants"
                error={participantsQuery.error}
                onRetry={participantsQuery.reload}
              />
            ) : !participantsQuery.latestData ? (
              <LoadingState label="Loading participants…" />
            ) : (
              <ParticipantList participants={participantsQuery.latestData} shifts={event.shifts} />
            ))}
        </div>
      </section>

      {dialog === "cancel" && (
        <ConfirmDialog
          title="Cancel this event?"
          confirmLabel="Cancel event"
          cancelLabel="Keep event"
          isBusy={isWorking}
          error={dialogError}
          onConfirm={handleCancelEvent}
          onCancel={() => setDialog(null)}
        >
          <p>
            Registration will close for every shift of <strong>{event.title}</strong>. The event,
            its shifts, and its {event.active_registrations} active registration
            {event.active_registrations === 1 ? "" : "s"} stay in the history.
          </p>
          <p>
            This doesn&apos;t send any notifications. Let registered peer educators know
            separately if needed. Cancelling can&apos;t be undone here.
          </p>
        </ConfirmDialog>
      )}

      {dialog === "delete" && (
        <ConfirmDialog
          title="Delete this draft permanently?"
          confirmLabel="Delete draft"
          cancelLabel="Keep draft"
          isBusy={isWorking}
          error={dialogError}
          onConfirm={handleDelete}
          onCancel={() => setDialog(null)}
        >
          <p>
            <strong>{event.title}</strong> and its {event.shift_count} shift
            {event.shift_count === 1 ? "" : "s"} will be removed. This can&apos;t be undone.
          </p>
        </ConfirmDialog>
      )}
    </>
  );
}
