import { useState } from "react";
import { Link } from "react-router-dom";
import EventForm from "../../components/supervisor/EventForm";
import { emptyEventValues } from "../../components/supervisor/eventFormValues";
import { ArrowLeftIcon } from "../../components/supervisor/Icons";
import { ErrorState, LoadingState } from "../../components/supervisor/StateViews";
import { useQuery } from "../../hooks/useQuery";
import { useEventsApi } from "../../services/events/useEventsApi";

const savedPath = (event) => `/supervisor/events/${event.event_id}`;

export default function EventCreate() {
  const api = useEventsApi();
  const [initialValues] = useState(emptyEventValues);
  const locationsQuery = useQuery("locations", () => api.getLocations());

  return (
    <>
      <Link to="/supervisor" className="back-link">
        <ArrowLeftIcon size={16} />
        All events
      </Link>
      <div className="page-header">
        <div>
          <h1 className="page-title">Create event</h1>
          <p className="page-subtitle">
            Add the event details and at least one shift. You&apos;ll be listed as the organizer.
          </p>
        </div>
      </div>

      {locationsQuery.error ? (
        <ErrorState
          title="We couldn't load locations"
          error={locationsQuery.error}
          onRetry={locationsQuery.reload}
        />
      ) : !locationsQuery.data ? (
        <LoadingState label="Loading form…" />
      ) : (
        <EventForm
          mode="create"
          initialValues={initialValues}
          locations={locationsQuery.data}
          onSubmit={api.createEvent}
          onCreateLocation={api.createLocation}
          cancelTo="/supervisor"
          getSavedPath={savedPath}
          savedNotice="Event created and published."
        />
      )}
    </>
  );
}
