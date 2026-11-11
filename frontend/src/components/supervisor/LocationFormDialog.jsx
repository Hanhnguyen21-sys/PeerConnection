import { useRef, useState } from "react";
import { validateLocation } from "../../lib/validation";
import { Modal } from "../Modal";

const FIELDS = ["building", "room_or_area", "directions", "map_url"];

export default function LocationFormDialog({ location = null, existingLocations, onSave, onClose }) {
  const isEdit = Boolean(location);
  const firstFieldRef = useRef(null);
  const savingRef = useRef(false);
  const [values, setValues] = useState(() =>
    Object.fromEntries(FIELDS.map((field) => [field, location?.[field] ?? ""])),
  );
  const [submitted, setSubmitted] = useState(false);
  const [serverErrors, setServerErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const clientErrors = submitted
    ? validateLocation(values, existingLocations, location?.location_id ?? null)
    : {};
  const errors = { ...serverErrors, ...clientErrors };

  function handleChange(event) {
    const { name, value } = event.target;
    setValues((current) => ({ ...current, [name]: value }));
    setServerErrors({});
  }

  async function handleSubmit(event) {
    // This form renders in a portal; keep its submit from reaching a parent form.
    event.preventDefault();
    event.stopPropagation();
    if (savingRef.current) return;

    setSubmitted(true);
    setFormError("");
    const nextErrors = validateLocation(values, existingLocations, location?.location_id ?? null);
    const firstInvalid = FIELDS.find((field) => nextErrors[field]);
    if (firstInvalid) {
      document.getElementById(`location-${firstInvalid}`)?.focus();
      return;
    }

    savingRef.current = true;
    setIsSaving(true);
    try {
      await onSave(values);
    } catch (error) {
      setServerErrors(error.fieldErrors ?? {});
      setFormError(error.message || "We couldn't save this location. Please try again.");
      savingRef.current = false;
      setIsSaving(false);
    }
  }

  const close = () => {
    if (!savingRef.current) onClose();
  };

  const describedBy = (field, hint) =>
    [hint && `location-${field}-hint`, errors[field] && `location-${field}-error`]
      .filter(Boolean)
      .join(" ") || undefined;

  const fieldError = (field) =>
    errors[field] ? (
      <p className="error-text" id={`location-${field}-error`}>
        {errors[field]}
      </p>
    ) : null;

  return (
    <Modal title={isEdit ? "Edit location" : "Add location"} onClose={close} initialFocusRef={firstFieldRef}>
      <form className="modal-body" onSubmit={handleSubmit} noValidate>
        {isEdit && (
          <p className="callout">
            Changes here update this location everywhere it&apos;s used
            {location.shift_count ? `, including ${location.shift_count} shift${location.shift_count === 1 ? "" : "s"}` : ""}.
            To move one shift somewhere else, choose a different location on that shift instead.
          </p>
        )}

        <div className="form-field">
          <label className="label" htmlFor="location-building">
            Building <span className="required">(required)</span>
          </label>
          <input
            ref={firstFieldRef}
            id="location-building"
            name="building"
            className="input"
            value={values.building}
            onChange={handleChange}
            aria-invalid={errors.building ? "true" : undefined}
            aria-describedby={describedBy("building")}
            autoComplete="off"
            required
          />
          {fieldError("building")}
        </div>

        <div className="form-field">
          <label className="label" htmlFor="location-room_or_area">
            Room or area <span className="required">(required)</span>
          </label>
          <input
            id="location-room_or_area"
            name="room_or_area"
            className="input"
            value={values.room_or_area}
            onChange={handleChange}
            aria-invalid={errors.room_or_area ? "true" : undefined}
            aria-describedby={describedBy("room_or_area")}
            autoComplete="off"
            required
          />
          {fieldError("room_or_area")}
        </div>

        <div className="form-field">
          <label className="label" htmlFor="location-directions">
            Directions
          </label>
          <textarea
            id="location-directions"
            name="directions"
            className="textarea"
            rows={3}
            value={values.directions}
            onChange={handleChange}
            aria-describedby={describedBy("directions", true)}
          />
          <p className="hint" id="location-directions-hint">
            Optional. How to find the room once inside the building.
          </p>
        </div>

        <div className="form-field">
          <label className="label" htmlFor="location-map_url">
            Map link
          </label>
          <input
            id="location-map_url"
            name="map_url"
            type="url"
            inputMode="url"
            className="input"
            placeholder="https://"
            value={values.map_url}
            onChange={handleChange}
            aria-invalid={errors.map_url ? "true" : undefined}
            aria-describedby={describedBy("map_url", true)}
          />
          <p className="hint" id="location-map_url-hint">
            Optional. A full http:// or https:// link, such as a Google Maps link.
          </p>
          {fieldError("map_url")}
        </div>

        <div className="form-alert" role="alert">
          {formError}
        </div>

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={close} disabled={isSaving}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={isSaving}>
            {isSaving && <span className="spinner" aria-hidden="true" />}
            {isSaving ? "Saving…" : isEdit ? "Save location" : "Add location"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
