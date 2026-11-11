let keyCounter = 0;

function newShiftKey() {
  keyCounter += 1;
  return `new-${keyCounter}`;
}

export function emptyShift(copyFrom = null) {
  return {
    key: newShiftKey(),
    shift_id: null,
    shift_date: copyFrom?.shift_date ?? "",
    start_time: "",
    end_time: "",
    location_id: copyFrom?.location_id ?? "",
    capacity: copyFrom?.capacity ?? "1",
    active_registrations: 0,
  };
}

export function emptyEventValues() {
  return { title: "", description: "", is_urgent: false, shifts: [emptyShift()] };
}

export function eventToFormValues(event) {
  return {
    title: event.title,
    description: event.description ?? "",
    is_urgent: Boolean(event.is_urgent),
    shifts: event.shifts.map((shift) => ({
      key: `shift-${shift.shift_id}`,
      shift_id: shift.shift_id,
      shift_date: shift.shift_date,
      start_time: shift.start_time,
      end_time: shift.end_time,
      location_id: String(shift.location_id),
      capacity: String(shift.capacity),
      active_registrations: shift.active_registrations,
    })),
  };
}

// Original values of saved shifts, used to lock shifts that have registrations.
export function lockedShiftsFrom(values) {
  return Object.fromEntries(
    values.shifts
      .filter((shift) => shift.shift_id != null)
      .map((shift) => [shift.shift_id, { ...shift }]),
  );
}

export function toEventPayload(values) {
  return {
    title: values.title,
    description: values.description,
    is_urgent: values.is_urgent,
    shifts: values.shifts.map((shift) => ({
      ...(shift.shift_id != null ? { shift_id: shift.shift_id } : {}),
      shift_date: shift.shift_date,
      start_time: shift.start_time,
      end_time: shift.end_time,
      location_id: shift.location_id === "" ? null : Number(shift.location_id),
      capacity: Number(shift.capacity),
    })),
  };
}

// Comparable snapshot for unsaved-change detection (ignores client-only keys).
export function snapshot(values) {
  return JSON.stringify({
    title: values.title,
    description: values.description,
    is_urgent: values.is_urgent,
    // eslint-disable-next-line no-unused-vars
    shifts: values.shifts.map(({ key, active_registrations, ...shift }) => shift),
  });
}
