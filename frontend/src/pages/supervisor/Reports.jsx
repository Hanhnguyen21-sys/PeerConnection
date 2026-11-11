import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingState } from "../../components/supervisor/StateViews";
import { useQuery } from "../../hooks/useQuery";
import {
  campusToday,
  CAMPUS_TIME_LABEL,
  endOfMonth,
  endOfWeek,
  formatDateRange,
  isValidDateString,
  startOfMonth,
  startOfWeek,
} from "../../lib/campusTime";
import { useEventsApi } from "../../services/events/useEventsApi";

const PRESETS = [
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
  { value: "custom", label: "Custom range" },
];

function formatFillRate(rate) {
  return rate === null ? "—" : `${Math.round(rate)}%`;
}

function resolveRange(preset, from, to) {
  const today = campusToday();
  if (preset === "month") return { from: startOfMonth(today), to: endOfMonth(today) };
  if (preset === "custom") {
    if (!isValidDateString(from) || !isValidDateString(to)) {
      return { error: "Choose both a start and an end date." };
    }
    if (from > to) return { error: "The start date must be on or before the end date." };
    return { from, to };
  }
  return { from: startOfWeek(today), to: endOfWeek(today) };
}

export default function Reports() {
  const api = useEventsApi();
  const [searchParams, setSearchParams] = useSearchParams();
  const presetParam = searchParams.get("range");
  const preset = PRESETS.some((p) => p.value === presetParam) ? presetParam : "week";
  const customFrom = searchParams.get("from") ?? "";
  const customTo = searchParams.get("to") ?? "";
  const range = resolveRange(preset, customFrom, customTo);

  const reportQuery = useQuery(range.error ? null : `${range.from}:${range.to}`, () =>
    api.getReport({ from: range.from, to: range.to }),
  );
  const report = reportQuery.latestData;

  function update(changes) {
    setSearchParams(
      (params) => {
        for (const [key, value] of Object.entries(changes)) {
          if (value) params.set(key, value);
          else params.delete(key);
        }
        return params;
      },
      { replace: true },
    );
  }

  function choosePreset(value) {
    if (value === "custom" && !customFrom && !customTo) {
      // Start the custom range from the current week so it's never empty.
      const today = campusToday();
      update({ range: value, from: startOfWeek(today), to: endOfWeek(today) });
    } else {
      update({ range: value === "week" ? null : value });
    }
  }

  const summary = report?.summary;
  const cards = summary
    ? [
        { label: "Events scheduled", value: summary.events_scheduled, hint: "With a shift in this range" },
        { label: "Active registrations", value: summary.active_registrations, hint: "Sign-ups, not attendance" },
        { label: "Unique peer educators", value: summary.unique_peer_educators, hint: "Distinct people registered" },
        { label: "Open spots", value: summary.open_spots, hint: `Of ${summary.total_capacity} total capacity` },
        { label: "Fill rate", value: formatFillRate(summary.fill_rate), hint: "Registrations ÷ capacity" },
        {
          label: "Understaffed shifts",
          value: summary.understaffed_shifts,
          hint: "Below capacity",
          warn: summary.understaffed_shifts > 0,
        },
      ]
    : [];

  let content;
  if (range.error) {
    content = null;
  } else if (reportQuery.error) {
    content = (
      <ErrorState title="We couldn't load this report" error={reportQuery.error} onRetry={reportQuery.reload} />
    );
  } else if (!report) {
    content = <LoadingState label="Calculating report…" />;
  } else {
    content = (
      <div className={reportQuery.isLoading ? "is-refreshing" : undefined} aria-busy={reportQuery.isLoading}>
        <dl className="stat-grid stat-grid-6">
          {cards.map((card) => (
            <div key={card.label} className={`stat-card${card.warn ? " stat-warn" : ""}`}>
              <dt>{card.label}</dt>
              <dd>{card.value}</dd>
              <p className="stat-hint">{card.hint}</p>
            </div>
          ))}
        </dl>

        <section className="card" aria-labelledby="report-table-heading">
          <h2 className="section-title" id="report-table-heading">
            Staffing by event
          </h2>
          {report.rows.length === 0 ? (
            <EmptyState title="No shifts in this range">
              Try a different date range. Cancelled and draft events aren&apos;t counted.
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">
                  Staffing by event for {formatDateRange(report.range.from, report.range.to)}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Event</th>
                    <th scope="col" className="num">
                      Shifts in range
                    </th>
                    <th scope="col" className="num">
                      Active registrations
                    </th>
                    <th scope="col" className="num">
                      Capacity
                    </th>
                    <th scope="col" className="num">
                      Open spots
                    </th>
                    <th scope="col">Fill rate</th>
                  </tr>
                </thead>
                <tbody>
                  {report.rows.map((row) => (
                    <tr key={row.event_id}>
                      <th scope="row" className="cell-title">
                        <Link className="text-link" to={`/supervisor/events/${row.event_id}`}>
                          {row.title}
                        </Link>
                      </th>
                      <td className="num">{row.shifts_in_range}</td>
                      <td className="num">{row.active_registrations}</td>
                      <td className="num">{row.capacity}</td>
                      <td className="num">{row.open_spots}</td>
                      <td>
                        <div className="fill-cell">
                          <span className="num">{formatFillRate(row.fill_rate)}</span>
                          <div className="meter" aria-hidden="true">
                            <span style={{ width: `${Math.min(row.fill_rate ?? 0, 100)}%` }} />
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Reports</h1>
          <p className="page-subtitle">
            Staffing for shifts that take place in the selected range. Cancelled and draft events are
            excluded.
          </p>
        </div>
      </div>

      <div className="filters" role="region" aria-label="Report range">
        <div className="filter-block">
          <span className="label" id="range-label">
            Date range
          </span>
          <div className="chip-group" role="group" aria-labelledby="range-label">
            {PRESETS.map((option) => (
              <button
                key={option.value}
                type="button"
                className="chip"
                aria-pressed={preset === option.value}
                onClick={() => choosePreset(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {preset === "custom" && (
          <fieldset className="filter-block date-range">
            <legend className="label">Custom range ({CAMPUS_TIME_LABEL})</legend>
            <div className="date-range-inputs">
              <div className="form-field">
                <label className="hint" htmlFor="report-from">
                  From
                </label>
                <input
                  id="report-from"
                  type="date"
                  className="input"
                  value={customFrom}
                  onChange={(event) => update({ from: event.target.value })}
                  aria-invalid={range.error ? "true" : undefined}
                  aria-describedby={range.error ? "report-range-error" : undefined}
                />
              </div>
              <div className="form-field">
                <label className="hint" htmlFor="report-to">
                  To
                </label>
                <input
                  id="report-to"
                  type="date"
                  className="input"
                  value={customTo}
                  onChange={(event) => update({ to: event.target.value })}
                  aria-invalid={range.error ? "true" : undefined}
                  aria-describedby={range.error ? "report-range-error" : undefined}
                />
              </div>
            </div>
            {range.error && (
              <p className="error-text" id="report-range-error">
                {range.error}
              </p>
            )}
          </fieldset>
        )}
      </div>

      {!range.error && (
        <p className="results-count">
          Showing {formatDateRange(range.from, range.to)} · weeks run Monday–Sunday, {CAMPUS_TIME_LABEL}
        </p>
      )}

      {content}
    </>
  );
}
