import { useState } from "react";
import { useQuery } from "../../hooks/useQuery";
import { formatDate, formatTimeRange, hasShiftStarted } from "../../lib/campusTime";
import { useEventsApi } from "../../services/events/useEventsApi";
import { EmptyState, ErrorState, LoadingState } from "./StateViews";

const STATUS_CHOICES = [
  ["attended", "Attended"],
  ["absent", "Absent"],
  ["", "Not marked"],
];

function shiftLabel(shift) {
  return `${formatDate(shift.shift_date)}, ${formatTimeRange(shift.start_time, shift.end_time)}`;
}

// The latest shift that has started, so supervisors land on the one they're most
// likely taking attendance for; otherwise the first shift.
function defaultShiftId(shifts) {
  const started = shifts.filter((shift) => hasShiftStarted(shift));
  const shift = started.length ? started[started.length - 1] : shifts[0];
  return shift ? String(shift.shift_id) : "";
}

function initialValues(roster) {
  const values = {};
  for (const entry of roster.roster) {
    values[entry.registration_id] = {
      status: entry.attendance?.participation_status ?? "",
      minutes:
        entry.attendance?.participation_status === "attended" ? String(entry.attendance.credited_minutes) : "",
    };
  }
  return values;
}

// Records to PUT (new or changed marks) and registrations to clear (marks removed).
function pendingChanges(roster, values) {
  const records = [];
  const clears = [];
  for (const entry of roster.roster) {
    const before = entry.attendance;
    const now = values[entry.registration_id];
    if (!now.status) {
      if (before) clears.push(entry.registration_id);
      continue;
    }
    const minutes = now.status === "attended" ? now.minutes.trim() : "";
    const changed =
      !before ||
      before.participation_status !== now.status ||
      (now.status === "attended" && minutes !== "" && Number(minutes) !== before.credited_minutes) ||
      (now.status === "attended" && minutes === "" && before.credited_minutes !== roster.shift.duration_minutes);
    if (changed) {
      records.push({
        registration_id: entry.registration_id,
        participation_status: now.status,
        ...(minutes !== "" ? { credited_minutes: minutes } : {}),
      });
    }
  }
  return { records, clears };
}

function AttendanceRoster({ roster, isSaving, saveError, rowErrors, onSave }) {
  const [values, setValues] = useState(() => initialValues(roster));
  const { records, clears } = pendingChanges(roster, values);
  const hasChanges = records.length + clears.length > 0;
  const readOnly = !roster.can_record;
  const { summary, shift } = roster;

  function setValue(registrationId, patch) {
    setValues((current) => ({ ...current, [registrationId]: { ...current[registrationId], ...patch } }));
  }

  function markEveryoneAttended() {
    setValues((current) => {
      const next = { ...current };
      for (const [id, value] of Object.entries(current)) {
        if (!value.status) next[id] = { status: "attended", minutes: "" };
      }
      return next;
    });
  }

  if (roster.roster.length === 0) {
    return (
      <EmptyState title="No one to mark">
        No peer educators have an active registration for this shift.
      </EmptyState>
    );
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (hasChanges && !readOnly) onSave(records, clears);
      }}
    >
      {readOnly && <div className="callout">{roster.blocked_reason}</div>}

      <p className="hint attendance-summary" role="status">
        {summary.registered} registered · {summary.attended} attended · {summary.absent} absent ·{" "}
        {summary.unmarked} not marked · {summary.credited_minutes} credited minutes
      </p>

      <div className="table-wrap">
        <table>
          <caption className="visually-hidden">Attendance for {shiftLabel(shift)}</caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Email</th>
              <th scope="col">Attendance</th>
              <th scope="col">Credited minutes</th>
            </tr>
          </thead>
          <tbody>
            {roster.roster.map((entry) => {
              const value = values[entry.registration_id];
              const error = rowErrors[entry.registration_id];
              const groupName = `attendance-${entry.registration_id}`;
              return (
                <tr key={entry.registration_id}>
                  <td>{entry.user.name}</td>
                  <td>
                    <a className="text-link" href={`mailto:${entry.user.email}`}>
                      {entry.user.email}
                    </a>
                  </td>
                  <td>
                    <fieldset className="attendance-choices" disabled={readOnly || isSaving}>
                      <legend className="visually-hidden">Attendance for {entry.user.name}</legend>
                      {STATUS_CHOICES.map(([status, label]) => (
                        <label key={status || "none"} className="attendance-choice">
                          <input
                            type="radio"
                            name={groupName}
                            value={status}
                            checked={value.status === status}
                            onChange={() => setValue(entry.registration_id, { status })}
                          />
                          {label}
                        </label>
                      ))}
                    </fieldset>
                    {error && (
                      <p className="error-text" role="alert">
                        {error}
                      </p>
                    )}
                  </td>
                  <td>
                    <label className="visually-hidden" htmlFor={`minutes-${entry.registration_id}`}>
                      Credited minutes for {entry.user.name}
                    </label>
                    <input
                      id={`minutes-${entry.registration_id}`}
                      className="input attendance-minutes"
                      type="number"
                      min="0"
                      max={shift.duration_minutes}
                      step="1"
                      inputMode="numeric"
                      placeholder={value.status === "attended" ? String(shift.duration_minutes) : "—"}
                      value={value.status === "attended" ? value.minutes : ""}
                      disabled={readOnly || isSaving || value.status !== "attended"}
                      aria-invalid={error ? "true" : undefined}
                      onChange={(event) => setValue(entry.registration_id, { minutes: event.target.value })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {!readOnly && (
        <>
          <p className="hint attendance-help">
            Attended defaults to the full shift ({shift.duration_minutes} minutes). Absent is always 0.
          </p>
          <div className="form-alert" role="alert">
            {saveError}
          </div>
          <div className="attendance-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={markEveryoneAttended}
              disabled={isSaving || summary.unmarked === 0}
            >
              Mark everyone not marked as attended
            </button>
            <button type="submit" className="btn btn-primary" disabled={isSaving || !hasChanges}>
              {isSaving && <span className="spinner" aria-hidden="true" />}
              {isSaving ? "Saving…" : "Save attendance"}
            </button>
          </div>
        </>
      )}
    </form>
  );
}

// Supervisor attendance for one shift at a time: who came, who didn't, and how
// many minutes each person is credited. Backed by /api/shifts/{id}/attendance.
export default function AttendancePanel({ shifts, onSaved }) {
  const api = useEventsApi();
  const [shiftId, setShiftId] = useState(() => defaultShiftId(shifts));
  const [saved, setSaved] = useState(null); // { shiftId, roster, version } from the last save
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [rowErrors, setRowErrors] = useState({});

  const rosterQuery = useQuery(shiftId ? `attendance:${shiftId}` : null, () => api.getShiftAttendance(shiftId));
  const roster = saved?.shiftId === shiftId ? saved.roster : rosterQuery.data;

  if (shifts.length === 0) {
    return <EmptyState title="No shifts">Add a shift to this event before taking attendance.</EmptyState>;
  }

  function changeShift(nextId) {
    setShiftId(nextId);
    setSaved(null);
    setSaveError("");
    setRowErrors({});
  }

  async function handleSave(records, clears) {
    setIsSaving(true);
    setSaveError("");
    setRowErrors({});
    try {
      let latest = null;
      if (records.length > 0) latest = await api.saveShiftAttendance(shiftId, records);
      for (const registrationId of clears) await api.clearAttendance(registrationId);
      if (clears.length > 0 || !latest) latest = await api.getShiftAttendance(shiftId);
      setSaved((current) => ({ shiftId, roster: latest, version: (current?.version ?? 0) + 1 }));
      onSaved?.(`Attendance saved for ${shiftLabel(latest.shift)}.`);
    } catch (error) {
      // The bulk endpoint reports field errors by the record's position in the request.
      const byIndex = error.fieldErrors?.records;
      if (byIndex && typeof byIndex === "object") {
        const errors = {};
        for (const [index, fields] of Object.entries(byIndex)) {
          const record = records[Number(index)];
          if (record) errors[record.registration_id] = Object.values(fields).join(" ");
        }
        setRowErrors(errors);
      }
      setSaveError(error.message || "We couldn't save attendance. Please try again.");
    } finally {
      setIsSaving(false);
    }
  }

  let content;
  if (rosterQuery.error && !roster) {
    content = (
      <ErrorState title="We couldn't load attendance" error={rosterQuery.error} onRetry={rosterQuery.reload} />
    );
  } else if (!roster) {
    content = <LoadingState label="Loading attendance…" />;
  } else {
    content = (
      <AttendanceRoster
        key={`${shiftId}:${saved?.shiftId === shiftId ? saved.version : 0}`}
        roster={roster}
        isSaving={isSaving}
        saveError={saveError}
        rowErrors={rowErrors}
        onSave={handleSave}
      />
    );
  }

  return (
    <>
      <div className="participant-toolbar">
        <div className="form-field">
          <label className="label" htmlFor="attendance-shift">
            Shift
          </label>
          <select
            id="attendance-shift"
            className="select"
            value={shiftId}
            onChange={(event) => changeShift(event.target.value)}
            disabled={isSaving}
          >
            {shifts.map((shift) => (
              <option key={shift.shift_id} value={String(shift.shift_id)}>
                {shiftLabel(shift)}
              </option>
            ))}
          </select>
        </div>
      </div>
      {content}
    </>
  );
}
