import { useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import EventCard from "../../components/supervisor/EventCard";
import { PlusIcon } from "../../components/supervisor/Icons";
import { EmptyState, ErrorState, LoadingState, Notice } from "../../components/supervisor/StateViews";
import { useQuery } from "../../hooks/useQuery";
import { CAMPUS_TIME_LABEL, isValidDateString } from "../../lib/campusTime";
import { useEventsApi } from "../../services/events/useEventsApi";

const STATUS_FILTERS = [
  { value: "all", label: "All" },
  { value: "upcoming", label: "Upcoming" },
  { value: "past", label: "Past" },
  { value: "cancelled", label: "Cancelled" },
];

export default function EventsHome() {
  const api = useEventsApi();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [notice, setNotice] = useState(location.state?.notice ?? "");

  const search = searchParams.get("q") ?? "";
  const statusParam = searchParams.get("status");
  const status = STATUS_FILTERS.some((f) => f.value === statusParam) ? statusParam : "all";
  const from = searchParams.get("from") ?? "";
  const to = searchParams.get("to") ?? "";
  const rangeInvalid = Boolean(from && to && from > to);

  const query = {
    search: search.trim(),
    status,
    from: !rangeInvalid && isValidDateString(from) ? from : undefined,
    to: !rangeInvalid && isValidDateString(to) ? to : undefined,
  };
  const eventsQuery = useQuery(JSON.stringify(query), () => api.getEvents(query));
  const events = eventsQuery.latestData;
  const hasFilters = Boolean(query.search || status !== "all" || from || to);

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
        title="No events match your filters"
        action={
          <button type="button" className="btn btn-secondary" onClick={clearFilters}>
            Clear filters
          </button>
        }
      >
        Try a different search or date range.
      </EmptyState>
    ) : (
      <EmptyState
        title="No events yet"
        action={
          <Link to="/supervisor/events/new" className="btn btn-primary">
            Create your first event
          </Link>
        }
      >
        Events you create will show up here with their staffing at a glance.
      </EmptyState>
    );
  } else {
    content = (
      <ul className={`event-grid${eventsQuery.isLoading ? " is-refreshing" : ""}`} aria-busy={eventsQuery.isLoading}>
        {events.map((event) => (
          <li key={event.event_id}>
            <EventCard event={event} />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Manage events</h1>
          <p className="page-subtitle">Track staffing for every event and shift.</p>
        </div>
        <Link to="/supervisor/events/new" className="btn btn-primary">
          <PlusIcon size={18} />
          Create event
        </Link>
      </div>

      <Notice onDismiss={() => setNotice("")}>{notice}</Notice>

      <div className="filters" aria-label="Event filters" role="region">
        <div className="filter-block">
          <span className="label" id="status-filter-label">
            Status
          </span>
          <div className="chip-group" role="group" aria-labelledby="status-filter-label">
            {STATUS_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                className="chip"
                aria-pressed={status === filter.value}
                onClick={() => setParam("status", filter.value)}
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
              <label className="hint" htmlFor="filter-from">
                From
              </label>
              <input
                id="filter-from"
                type="date"
                className="input"
                value={from}
                max={to || undefined}
                onChange={(event) => setParam("from", event.target.value)}
                aria-invalid={rangeInvalid ? "true" : undefined}
                aria-describedby={rangeInvalid ? "date-range-error" : undefined}
              />
            </div>
            <div className="form-field">
              <label className="hint" htmlFor="filter-to">
                To
              </label>
              <input
                id="filter-to"
                type="date"
                className="input"
                value={to}
                min={from || undefined}
                onChange={(event) => setParam("to", event.target.value)}
                aria-invalid={rangeInvalid ? "true" : undefined}
                aria-describedby={rangeInvalid ? "date-range-error" : undefined}
              />
            </div>
            {hasFilters && (
              <button type="button" className="btn-text" onClick={clearFilters}>
                Clear filters
              </button>
            )}
          </div>
          {rangeInvalid && (
            <p className="error-text" id="date-range-error">
              The start date must be on or before the end date. The date filter is paused until
              it&apos;s fixed.
            </p>
          )}
        </fieldset>
      </div>

      <p className="results-count" role="status">
        {events && !eventsQuery.error
          ? `${events.length} event${events.length === 1 ? "" : "s"}${query.search ? ` matching “${query.search}”` : ""}`
          : ""}
      </p>

      {content}
    </>
  );
}
