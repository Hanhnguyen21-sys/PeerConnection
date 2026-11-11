// Validation shared by the forms and the demo service. The backend must repeat
// these checks; running them here only gives faster, friendlier feedback.
import { isValidDateString, isValidTimeString } from "./campusTime";

export const MAX_TITLE_LENGTH = 120;
export const MAX_CAPACITY = 500;

export function normalizeText(value) {
  return (value ?? "").trim().replace(/\s+/g, " ");
}

export function locationKey(location) {
  return `${normalizeText(location.building).toLowerCase()}|${normalizeText(
    location.room_or_area,
  ).toLowerCase()}`;
}

export function isHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

// Returns a link that is safe to open, or null.
export function safeExternalUrl(value) {
  return value && isHttpUrl(value) ? value : null;
}

export function cleanLocationInput(values) {
  return {
    building: normalizeText(values.building),
    room_or_area: normalizeText(values.room_or_area),
    directions: (values.directions ?? "").trim() || null,
    map_url: (values.map_url ?? "").trim() || null,
  };
}

export function validateLocation(values, existingLocations = [], currentId = null) {
  const errors = {};
  const cleaned = cleanLocationInput(values);
  if (!cleaned.building) errors.building = "Enter a building.";
  if (!cleaned.room_or_area) errors.room_or_area = "Enter a room or area.";
  if (cleaned.map_url && !isHttpUrl(cleaned.map_url)) {
    errors.map_url = "Enter a full link that starts with http:// or https://.";
  }
  if (!errors.building && !errors.room_or_area) {
    const key = locationKey(cleaned);
    const duplicate = existingLocations.some(
      (location) => location.location_id !== currentId && locationKey(location) === key,
    );
    if (duplicate) {
      errors.room_or_area = "A location with this building and room or area already exists.";
    }
  }
  return errors;
}

function parseCapacity(value) {
  const text = String(value ?? "").trim();
  if (!/^\d+$/.test(text)) return null;
  return Number(text);
}

/**
 * Validates an event and its shifts.
 * - lockedShifts maps shift_id -> { shift_date, start_time, end_time, active_registrations }
 *   for saved shifts; shifts with active registrations keep their date and time.
 * - locationIds, when given, is a Set of valid location ids.
 * Returns { title?, shifts?, shiftFields: { [index]: { field: message } } }.
 */
export function validateEventInput(input, { lockedShifts = {}, locationIds = null } = {}) {
  const errors = { shiftFields: {} };
  const title = normalizeText(input.title);
  if (!title) errors.title = "Enter an event title.";
  else if (title.length > MAX_TITLE_LENGTH) {
    errors.title = `Keep the title under ${MAX_TITLE_LENGTH} characters.`;
  }

  const shifts = input.shifts ?? [];
  if (shifts.length === 0) errors.shifts = "Add at least one shift.";

  shifts.forEach((shift, index) => {
    const fieldErrors = {};
    const locked = shift.shift_id != null ? lockedShifts[shift.shift_id] : null;
    const activeRegistrations = locked?.active_registrations ?? 0;

    if (!shift.shift_date) fieldErrors.shift_date = "Choose a date.";
    else if (!isValidDateString(shift.shift_date)) fieldErrors.shift_date = "Enter a valid date.";

    if (!shift.start_time) fieldErrors.start_time = "Choose a start time.";
    else if (!isValidTimeString(shift.start_time)) fieldErrors.start_time = "Enter a valid time.";

    if (!shift.end_time) fieldErrors.end_time = "Choose an end time.";
    else if (!isValidTimeString(shift.end_time)) fieldErrors.end_time = "Enter a valid time.";
    else if (!fieldErrors.start_time && shift.start_time && shift.end_time <= shift.start_time) {
      fieldErrors.end_time = "End time must be after the start time on the same day.";
    }

    if (shift.location_id === "" || shift.location_id == null) {
      fieldErrors.location_id = "Choose a location.";
    } else if (locationIds && !locationIds.has(Number(shift.location_id))) {
      fieldErrors.location_id = "Choose a location from the list.";
    }

    const capacity = parseCapacity(shift.capacity);
    if (capacity === null || capacity < 1) {
      fieldErrors.capacity = "Enter a whole number of 1 or more.";
    } else if (capacity > MAX_CAPACITY) {
      fieldErrors.capacity = `Capacity can't be more than ${MAX_CAPACITY}.`;
    } else if (capacity < activeRegistrations) {
      fieldErrors.capacity = `Capacity can't be lower than the ${activeRegistrations} active registrations.`;
    }

    if (locked && activeRegistrations > 0) {
      const moved =
        shift.shift_date !== locked.shift_date ||
        shift.start_time !== locked.start_time ||
        shift.end_time !== locked.end_time;
      if (moved) {
        fieldErrors.shift_date =
          "This shift has active registrations, so its date and time can't change yet.";
      }
    }

    if (Object.keys(fieldErrors).length > 0) errors.shiftFields[index] = fieldErrors;
  });

  return errors;
}

export function hasEventErrors(errors) {
  return Boolean(errors.title || errors.shifts || Object.keys(errors.shiftFields ?? {}).length);
}
