import { useSearchParams } from "react-router-dom";
import EducatorEventCard from "../../components/educator/EducatorEventCard";
import { EmptyState, ErrorState, LoadingState } from "../../components/supervisor/StateViews";
import { useQuery } from "../../hooks/useQuery";
import { CAMPUS_TIME_LABEL, isValidDateString } from "../../lib/campusTime";
import { useEventsApi } from "../../services/events/useEventsApi";

const AVAILABILITY_FILTERS = [
  { value: "all", label: "All upcoming" },
  { value: "open", label: "Has open spots" },
];

export default function ExploreEvents() {
  const api = useEventsApi();
  const [searchParams, setSearchParams] = useSearchParams();

  const search = searchParams.get("q") ?? "";
  const availabilityParam = searchParams.get("availability");
  const availability = AVAILABILITY_FILTERS.some((f) => f.value === availabilityParam)
    ? availabilityParam
    : "all";
  const from = searchParams.get("from") ?? "";
  const to = searchParams.get("to") ?? "";
  const rangeInvalid = Boolean(from && to && from > to);

  const query = {
    search: search.trim(),
    availability,
    from: !rangeInvalid && isValidDateString(from) ? from : undefined,
    to: !rangeInvalid && isValidDateString(to) ? to : undefined,
  };
  const eventsQuery = useQuery(JSON.stringify(query), () => api.getAvailableEvents(query));
  const events = eventsQuery.latestData;
  const hasFilters = Boolean(query.search || availability !== "all" || from || to);

  function setParam(name, value) {
    setSearchParams(
      (params) => {
        if (value && value !== "all") params.set(name, value);
        else params.delete(name);
        return params;
      },
      { replace: true },
    );
  }

  function clearFilters() {
    setSearchParams({}, { replace: true });
  }

  let content;
  if (eventsQuery.error) {
    content = (
      <ErrorState title="We couldn't load events" error={eventsQuery.error} onRetry={eventsQuery.reload} />
    );
  } else if (!events) {
    content = <LoadingState label="Loading events…" />;
  } else if (events.length === 0) {
    content = hasFilters ? (
      <EmptyState
        title={query.search ? `No events match “${query.search}”` : "No events match your filters"}
        action={
          <button type="button" className="btn btn-secondary" onClick={clearFilters}>
            Clear filters
          </button>
        }
      >
        Try a different search, date range, or availability.
      </EmptyState>
    ) : (
      <EmptyState title="No upcoming events">
        There aren&apos;t any events with upcoming shifts right now. Check back soon.
      </EmptyState>
    );
  } else {
    content = (
      <ul className={`event-grid${eventsQuery.isLoading ? " is-refreshing" : ""}`} aria-busy={eventsQuery.isLoading}>
        {events.map((event) => (
          <li key={event.event_id}>
            <EducatorEventCard event={event} />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Explore events</h1>
          <p className="page-subtitle">
            Find a shift that fits your schedule. Registration is immediate, with no approval needed.
          </p>
        </div>
      </div>

      <div className="filters" role="region" aria-label="Event filters">
        <div className="filter-block">
          <span className="label" id="availability-filter-label">
            Availability
          </span>
          <div className="chip-group" role="group" aria-labelledby="availability-filter-label">
            {AVAILABILITY_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                className="chip"
                aria-pressed={availability === filter.value}
                onClick={() => setParam("availability", filter.value)}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>

        <fieldset className="filter-block date-range">
          <legend className="label">Shift dates ({CAMPUS_TIME_LABEL})</legend>
          <div className="date-range-inputs">
            <div className="form-field">
              <label className="hint" htmlFor="explore-from">
                From
              </label>
              <input
                id="explore-from"
                type="date"
                className="input"
                value={from}
                max={to || undefined}
                onChange={(event) => setParam("from", event.target.value)}
                aria-invalid={rangeInvalid ? "true" : undefined}
                aria-describedby={rangeInvalid ? "explore-range-error" : undefined}
              />
            </div>
            <div className="form-field">
              <label className="hint" htmlFor="explore-to">
                To
              </label>
              <input
                id="explore-to"
                type="date"
                className="input"
                value={to}
                min={from || undefined}
                onChange={(event) => setParam("to", event.target.value)}
                aria-invalid={rangeInvalid ? "true" : undefined}
                aria-describedby={rangeInvalid ? "explore-range-error" : undefined}
              />
            </div>
            {hasFilters && (
              <button type="button" className="btn-text" onClick={clearFilters}>
                Clear filters
              </button>
            )}
          </div>
          {rangeInvalid && (
            <p className="error-text" id="explore-range-error">
              The start date must be on or before the end date. The date filter is paused until
              it&apos;s fixed.
            </p>
          )}
        </fieldset>
      </div>

      <p className="results-count" role="status">
        {events && !eventsQuery.error
          ? `${events.length} upcoming event${events.length === 1 ? "" : "s"}${query.search ? ` matching “${query.search}”` : ""}`
          : ""}
      </p>

      {content}
    </>
  );
}
