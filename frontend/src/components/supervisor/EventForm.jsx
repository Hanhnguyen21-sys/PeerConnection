import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useBeforeUnload, useBlocker, useNavigate } from "react-router-dom";
import { CAMPUS_TIME_LABEL } from "../../lib/campusTime";
import { hasEventErrors, MAX_CAPACITY, MAX_TITLE_LENGTH, validateEventInput } from "../../lib/validation";
import { ConfirmDialog } from "../Modal";
import { emptyShift, lockedShiftsFrom, snapshot, toEventPayload } from "./eventFormValues";
import { LockIcon, PlusIcon, TrashIcon } from "./Icons";
import LocationFormDialog from "./LocationFormDialog";

const SHIFT_FIELDS = ["shift_date", "start_time", "end_time", "location_id", "capacity"];

function locationLabel(location) {
  return `${location.building} · ${location.room_or_area}`;
}

function sortLocations(list) {
  return [...list].sort(
    (a, b) => a.building.localeCompare(b.building) || a.room_or_area.localeCompare(b.room_or_area),
  );
}

function firstErrorId(errors, shifts) {
  if (errors.title) return "event-title";
  if (errors.shifts) return "add-shift";
  for (const [index, shift] of shifts.entries()) {
    const fieldErrors = errors.shiftFields[index];
    const field = fieldErrors && SHIFT_FIELDS.find((name) => fieldErrors[name]);
    if (field) return `shift-${shift.key}-${field}`;
  }
  return null;
}

export default function EventForm({
  mode,
  initialValues,
  locations,
  onSubmit,
  onCreateLocation,
  cancelTo,
  getSavedPath,
  savedNotice,
}) {
  const navigate = useNavigate();
  const isEdit = mode === "edit";
  const [values, setValues] = useState(initialValues);
  const [initialSnapshot] = useState(() => snapshot(initialValues));
  const [lockedShifts] = useState(() => lockedShiftsFrom(initialValues));
  const [locationOptions, setLocationOptions] = useState(() => sortLocations(locations));
  const [submitted, setSubmitted] = useState(false);
  const [serverErrors, setServerErrors] = useState(null);
  const [formError, setFormError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [savedPath, setSavedPath] = useState(null);
  const [locationDialogIndex, setLocationDialogIndex] = useState(null);
  const [announcement, setAnnouncement] = useState("");
  const [focusTarget, setFocusTarget] = useState(null);
  const savingRef = useRef(false);

  const locationIds = useMemo(
    () => new Set(locationOptions.map((location) => location.location_id)),
    [locationOptions],
  );
  const clientErrors = submitted ? validateEventInput(values, { lockedShifts, locationIds }) : null;
  const errors =
    clientErrors && hasEventErrors(clientErrors) ? clientErrors : (serverErrors ?? { shiftFields: {} });

  const isDirty = !savedPath && snapshot(values) !== initialSnapshot;

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  );

  useBeforeUnload(
    useCallback(
      (event) => {
        if (isDirty) {
          event.preventDefault();
          event.returnValue = "";
        }
      },
      [isDirty],
    ),
  );

  useEffect(() => {
    if (savedPath) navigate(savedPath, { state: { notice: savedNotice } });
  }, [savedPath, savedNotice, navigate]);

  useEffect(() => {
    if (focusTarget) document.getElementById(focusTarget.id)?.focus();
  }, [focusTarget]);

  function updateValues(update) {
    setValues(update);
    setServerErrors(null);
  }

  function updateField(event) {
    const { name, type, checked, value } = event.target;
    updateValues((current) => ({ ...current, [name]: type === "checkbox" ? checked : value }));
  }

  function updateShift(index, field, value) {
    updateValues((current) => ({
      ...current,
      shifts: current.shifts.map((shift, i) => (i === index ? { ...shift, [field]: value } : shift)),
    }));
  }

  function addShift() {
    const shift = emptyShift(values.shifts.at(-1));
    updateValues((current) => ({ ...current, shifts: [...current.shifts, shift] }));
    setFocusTarget({ id: `shift-${shift.key}-shift_date` });
    setAnnouncement(`Shift ${values.shifts.length + 1} added.`);
  }

  function removeShift(index) {
    updateValues((current) => ({
      ...current,
      shifts: current.shifts.filter((_, i) => i !== index),
    }));
    setFocusTarget({ id: "add-shift" });
    setAnnouncement(`Shift ${index + 1} removed.`);
  }

  async function handleCreateLocation(input) {
    const location = await onCreateLocation(input);
    const index = locationDialogIndex;
    setLocationOptions((current) => sortLocations([...current, location]));
    updateValues((current) => ({
      ...current,
      shifts: current.shifts.map((shift, i) =>
        i === index ? { ...shift, location_id: String(location.location_id) } : shift,
      ),
    }));
    setLocationDialogIndex(null);
    setAnnouncement(`${locationLabel(location)} added and selected for shift ${index + 1}.`);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (savingRef.current) return;

    setSubmitted(true);
    setFormError("");
    setServerErrors(null);
    const nextErrors = validateEventInput(values, { lockedShifts, locationIds });
    if (hasEventErrors(nextErrors)) {
      setFormError("Please fix the highlighted fields.");
      setFocusTarget({ id: firstErrorId(nextErrors, values.shifts) });
      return;
    }

    savingRef.current = true;
    setIsSaving(true);
    try {
      const saved = await onSubmit(toEventPayload(values));
      setSavedPath(getSavedPath(saved));
    } catch (error) {
      savingRef.current = false;
      setIsSaving(false);
      if (error.fieldErrors) setServerErrors({ shiftFields: {}, ...error.fieldErrors });
      setFormError(error.message || "We couldn't save this event. Please try again.");
    }
  }

  const describedBy = (...ids) => ids.filter(Boolean).join(" ") || undefined;

  return (
    <>
      <form className="event-form" onSubmit={handleSubmit} noValidate aria-busy={isSaving}>
        <section className="card form-section" aria-labelledby="event-details-heading">
          <h2 className="section-title" id="event-details-heading">
            Event details
          </h2>

          <div className="form-field">
            <label className="label" htmlFor="event-title">
              Title <span className="required">(required)</span>
            </label>
            <input
              id="event-title"
              name="title"
              className="input"
              value={values.title}
              onChange={updateField}
              maxLength={MAX_TITLE_LENGTH}
              aria-invalid={errors.title ? "true" : undefined}
              aria-describedby={errors.title ? "event-title-error" : undefined}
              required
            />
            {errors.title && (
              <p className="error-text" id="event-title-error">
                {errors.title}
              </p>
            )}
          </div>

          <div className="form-field">
            <label className="label" htmlFor="event-description">
              Description
            </label>
            <textarea
              id="event-description"
              name="description"
              className="textarea"
              rows={4}
              value={values.description}
              onChange={updateField}
            />
          </div>

          <div className="checkbox-field">
            <input
              id="event-urgent"
              name="is_urgent"
              type="checkbox"
              checked={values.is_urgent}
              onChange={updateField}
              aria-describedby="event-urgent-hint"
            />
            <div>
              <label className="label" htmlFor="event-urgent">
                Mark as urgent
              </label>
              <p className="hint" id="event-urgent-hint">
                Shows an Urgent badge so peer educators notice this event first.
              </p>
            </div>
          </div>
        </section>

        <section className="card form-section" aria-labelledby="shifts-heading">
          <div className="section-heading-row">
            <div>
              <h2 className="section-title" id="shifts-heading">
                Shifts
              </h2>
              <p className="hint">
                Times are campus time ({CAMPUS_TIME_LABEL}). Each shift starts and ends on the same day.
              </p>
            </div>
          </div>

          {errors.shifts && (
            <p className="error-text" id="shifts-error">
              {errors.shifts}
            </p>
          )}

          {values.shifts.map((shift, index) => {
            const fieldErrors = errors.shiftFields[index] ?? {};
            const locked = shift.shift_id != null && shift.active_registrations > 0;
            const id = (field) => `shift-${shift.key}-${field}`;
            const errorId = (field) => (fieldErrors[field] ? `${id(field)}-error` : null);
            const lockId = locked ? `${id("lock")}` : null;
            const minCapacity = Math.max(1, shift.active_registrations);
            const fieldError = (field) =>
              fieldErrors[field] ? (
                <p className="error-text" id={`${id(field)}-error`}>
                  {fieldErrors[field]}
                </p>
              ) : null;

            return (
              <fieldset className="shift-fieldset" key={shift.key}>
                <legend className="shift-legend">Shift {index + 1}</legend>
                <button
                  type="button"
                  className="btn-text btn-text-danger shift-remove"
                  onClick={() => removeShift(index)}
                  disabled={locked || values.shifts.length === 1}
                  aria-describedby={describedBy(lockId)}
                  title={
                    locked
                      ? "Shifts with active registrations can't be removed yet."
                      : values.shifts.length === 1
                        ? "An event needs at least one shift."
                        : undefined
                  }
                >
                  <TrashIcon size={16} />
                  Remove<span className="visually-hidden"> shift {index + 1}</span>
                </button>

                {locked && (
                  <p className="lock-note" id={lockId}>
                    <LockIcon size={16} />
                    <span>
                      {shift.active_registrations} active registration
                      {shift.active_registrations === 1 ? "" : "s"}. The date and time can&apos;t
                      change and the shift can&apos;t be removed until the backend can check for
                      schedule conflicts. You can still change the location or raise the capacity.
                    </span>
                  </p>
                )}

                <div className="shift-grid">
                  <div className="form-field">
                    <label className="label" htmlFor={id("shift_date")}>
                      Date
                    </label>
                    <input
                      id={id("shift_date")}
                      type="date"
                      className="input"
                      value={shift.shift_date}
                      onChange={(event) => updateShift(index, "shift_date", event.target.value)}
                      disabled={locked}
                      aria-invalid={fieldErrors.shift_date ? "true" : undefined}
                      aria-describedby={describedBy(errorId("shift_date"), lockId)}
                      required
                    />
                    {fieldError("shift_date")}
                  </div>
                  <div className="form-field">
                    <label className="label" htmlFor={id("start_time")}>
                      Start time
                    </label>
                    <input
                      id={id("start_time")}
                      type="time"
                      className="input"
                      value={shift.start_time}
                      onChange={(event) => updateShift(index, "start_time", event.target.value)}
                      disabled={locked}
                      aria-invalid={fieldErrors.start_time ? "true" : undefined}
                      aria-describedby={describedBy(errorId("start_time"), lockId)}
                      required
                    />
                    {fieldError("start_time")}
                  </div>
                  <div className="form-field">
                    <label className="label" htmlFor={id("end_time")}>
                      End time
                    </label>
                    <input
                      id={id("end_time")}
                      type="time"
                      className="input"
                      value={shift.end_time}
                      onChange={(event) => updateShift(index, "end_time", event.target.value)}
                      disabled={locked}
                      aria-invalid={fieldErrors.end_time ? "true" : undefined}
                      aria-describedby={describedBy(errorId("end_time"), lockId)}
                      required
                    />
                    {fieldError("end_time")}
                  </div>
                  <div className="form-field">
                    <label className="label" htmlFor={id("capacity")}>
                      Capacity
                    </label>
                    <input
                      id={id("capacity")}
                      type="number"
                      inputMode="numeric"
                      className="input"
                      min={minCapacity}
                      max={MAX_CAPACITY}
                      step={1}
                      value={shift.capacity}
                      onChange={(event) => updateShift(index, "capacity", event.target.value)}
                      aria-invalid={fieldErrors.capacity ? "true" : undefined}
                      aria-describedby={describedBy(
                        errorId("capacity"),
                        locked ? `${id("capacity")}-hint` : null,
                      )}
                      required
                    />
                    {locked && (
                      <p className="hint" id={`${id("capacity")}-hint`}>
                        Minimum {shift.active_registrations}
                      </p>
                    )}
                    {fieldError("capacity")}
                  </div>
                </div>

                <div className="form-field">
                  <label className="label" htmlFor={id("location_id")}>
                    Location
                  </label>
                  <div className="location-row">
                    <select
                      id={id("location_id")}
                      className="select"
                      value={shift.location_id}
                      onChange={(event) => updateShift(index, "location_id", event.target.value)}
                      aria-invalid={fieldErrors.location_id ? "true" : undefined}
                      aria-describedby={describedBy(errorId("location_id"))}
                      required
                    >
                      <option value="">Choose a location</option>
                      {locationOptions.map((location) => (
                        <option key={location.location_id} value={String(location.location_id)}>
                          {locationLabel(location)}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => setLocationDialogIndex(index)}
                    >
                      <PlusIcon size={16} />
                      Add location
                      <span className="visually-hidden"> for shift {index + 1}</span>
                    </button>
                  </div>
                  {fieldError("location_id")}
                </div>
              </fieldset>
            );
          })}

          <button type="button" id="add-shift" className="btn btn-secondary add-shift" onClick={addShift}>
            <PlusIcon size={18} />
            Add shift
          </button>
        </section>

        <div className="form-alert" role="alert">
          {formError}
        </div>

        <div className="form-actions">
          <button type="button" className="btn btn-secondary" onClick={() => navigate(cancelTo)}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={isSaving}>
            {isSaving && <span className="spinner" aria-hidden="true" />}
            {isSaving ? "Saving…" : isEdit ? "Save changes" : "Create event"}
          </button>
        </div>

        <p className="visually-hidden" role="status" aria-live="polite">
          {announcement}
        </p>
      </form>

      {locationDialogIndex !== null && (
        <LocationFormDialog
          existingLocations={locationOptions}
          onSave={handleCreateLocation}
          onClose={() => setLocationDialogIndex(null)}
        />
      )}

      {blocker.state === "blocked" && (
        <ConfirmDialog
          title="Discard unsaved changes?"
          confirmLabel="Discard changes"
          cancelLabel="Keep editing"
          onConfirm={() => blocker.proceed()}
          onCancel={() => blocker.reset()}
        >
          <p>You have unsaved changes to this event. If you leave now, they&apos;ll be lost.</p>
        </ConfirmDialog>
      )}
    </>
  );
}
