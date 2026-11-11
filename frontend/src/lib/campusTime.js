// Campus-time helpers. Shift dates are plain "YYYY-MM-DD" strings and times are
// "HH:MM" wall-clock strings in America/Los_Angeles. Date math runs in UTC on
// those strings so a date never shifts because of the viewer's own time zone.

export const CAMPUS_TIME_ZONE = "America/Los_Angeles";
export const CAMPUS_TIME_LABEL = "Pacific Time";

const campusPartsFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: CAMPUS_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function campusNow(now = new Date()) {
  const parts = Object.fromEntries(
    campusPartsFormatter.formatToParts(now).map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
  };
}

export function campusToday() {
  return campusNow().date;
}

const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;

export function isValidDateString(value) {
  const match = DATE_PATTERN.exec(value ?? "");
  if (!match) return false;
  const [, year, month, day] = match.map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

export function isValidTimeString(value) {
  return TIME_PATTERN.test(value ?? "");
}

function toUtcDate(dateString) {
  const [year, month, day] = dateString.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function toDateString(date) {
  return date.toISOString().slice(0, 10);
}

export function addDays(dateString, days) {
  const date = toUtcDate(dateString);
  date.setUTCDate(date.getUTCDate() + days);
  return toDateString(date);
}

// Weeks run Monday through Sunday.
export function startOfWeek(dateString) {
  const offset = (toUtcDate(dateString).getUTCDay() + 6) % 7;
  return addDays(dateString, -offset);
}

export function endOfWeek(dateString) {
  return addDays(startOfWeek(dateString), 6);
}

export function startOfMonth(dateString) {
  return `${dateString.slice(0, 8)}01`;
}

export function endOfMonth(dateString) {
  const [year, month] = dateString.split("-").map(Number);
  return toDateString(new Date(Date.UTC(year, month, 0)));
}

const longDateFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
});

const shortDateFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  month: "short",
  day: "numeric",
});

const partsDateFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  weekday: "short",
  month: "short",
  day: "numeric",
});

export function formatDate(dateString) {
  return longDateFormatter.format(toUtcDate(dateString));
}

export function formatShortDate(dateString) {
  return shortDateFormatter.format(toUtcDate(dateString));
}

export function getDateParts(dateString) {
  const parts = Object.fromEntries(
    partsDateFormatter.formatToParts(toUtcDate(dateString)).map((part) => [part.type, part.value]),
  );
  return { weekday: parts.weekday, month: parts.month, day: parts.day };
}

const mediumDateFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  month: "short",
  day: "numeric",
  year: "numeric",
});

export function formatDateRange(start, end) {
  if (!start) return "No shifts scheduled";
  if (!end || start === end) return formatDate(start);
  const sameYear = start.slice(0, 4) === end.slice(0, 4);
  const startLabel = sameYear
    ? formatShortDate(start)
    : mediumDateFormatter.format(toUtcDate(start));
  return `${startLabel} – ${mediumDateFormatter.format(toUtcDate(end))}`;
}

export function formatTime(timeString) {
  const [hours, minutes] = timeString.split(":").map(Number);
  const suffix = hours >= 12 ? "PM" : "AM";
  return `${hours % 12 || 12}:${String(minutes).padStart(2, "0")} ${suffix}`;
}

export function formatTimeRange(start, end) {
  return `${formatTime(start)} – ${formatTime(end)} PT`;
}

const timestampFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: CAMPUS_TIME_ZONE,
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});

export function formatTimestamp(isoString) {
  return timestampFormatter.format(new Date(isoString));
}

export function hasShiftEnded(shift, now = campusNow()) {
  return (
    shift.shift_date < now.date ||
    (shift.shift_date === now.date && shift.end_time <= now.time)
  );
}

export function hasShiftStarted(shift, now = campusNow()) {
  return (
    shift.shift_date < now.date ||
    (shift.shift_date === now.date && shift.start_time <= now.time)
  );
}

// Same-day intervals overlap when newStart < existingEnd and newEnd > existingStart,
// so back-to-back shifts (10:00–11:00 and 11:00–12:00) do not overlap.
export function shiftsOverlap(a, b) {
  return a.shift_date === b.shift_date && a.start_time < b.end_time && a.end_time > b.start_time;
}

export function compareShifts(a, b) {
  return (
    a.shift_date.localeCompare(b.shift_date) ||
    a.start_time.localeCompare(b.start_time) ||
    a.end_time.localeCompare(b.end_time)
  );
}
