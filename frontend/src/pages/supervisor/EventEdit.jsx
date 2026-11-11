import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import EventForm from "../../components/supervisor/EventForm";
import { eventToFormValues } from "../../components/supervisor/eventFormValues";
import { ArrowLeftIcon } from "../../components/supervisor/Icons";
import { EmptyState, ErrorState, LoadingState } from "../../components/supervisor/StateViews";
import { useQuery } from "../../hooks/useQuery";
import { isNotFoundError } from "../../services/errors";
import { useEventsApi } from "../../services/events/useEventsApi";

const savedPath = (event) => `/supervisor/events/${event.event_id}`;

export default function EventEdit() {
  const { eventId } = useParams();
  const api = useEventsApi();
  const eventQuery = useQuery(`event:${eventId}`, () => api.getEvent(eventId));
  const locationsQuery = useQuery("locations", () => api.getLocations());
  const event = eventQuery.data;
  const initialValues = useMemo(() => (event ? eventToFormValues(event) : null), [event]);
  const detailPath = `/supervisor/events/${eventId}`;

  let content;
  if (isNotFoundError(eventQuery.error)) {
    content = (
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
  } else if (eventQuery.error || locationsQuery.error) {
    content = (
      <ErrorState
        title="We couldn't load this event"
        error={eventQuery.error ?? locationsQuery.error}
        onRetry={() => {
          eventQuery.reload();
          locationsQuery.reload();
        }}
      />
    );
  } else if (!event || !locationsQuery.data) {
    content = <LoadingState label="Loading event…" />;
  } else if (event.status === "cancelled") {
    content = (
      <EmptyState
        title="Cancelled events can't be edited"
        action={
          <Link to={detailPath} className="btn btn-secondary">
            View event
          </Link>
        }
      >
        Registration is closed and the event&apos;s history is kept as it was.
      </EmptyState>
    );
  } else {
    content = (
      <EventForm
        key={event.event_id}
        mode="edit"
        initialValues={initialValues}
        locations={locationsQuery.data}
        onSubmit={(input) => api.updateEvent(event.event_id, input)}
        onCreateLocation={api.createLocation}
        cancelTo={detailPath}
        getSavedPath={savedPath}
        savedNotice="Changes saved."
      />
    );
  }

  return (
    <>
      <Link to={detailPath} className="back-link">
        <ArrowLeftIcon size={16} />
        Back to event
      </Link>
      <div className="page-header">
        <div>
          <h1 className="page-title">Edit event</h1>
          {event && <p className="page-subtitle">{event.title}</p>}
        </div>
      </div>
      {content}
    </>
  );
}
