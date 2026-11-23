// Demo implementation of the event data service. Every function mirrors a
// proposed FastAPI endpoint (see API_CONTRACT.md) and returns the same shapes,
// so pages don't know whether data is demo or real.
import {
  campusNow,
  compareShifts,
  formatDate,
  formatTimeRange,
  hasShiftEnded,
  hasShiftStarted,
  isValidDateString,
  shiftsOverlap,
} from "../../lib/campusTime";
import {
  cleanLocationInput,
  hasEventErrors,
  normalizeText,
  validateEventInput,
  validateLocation,
} from "../../lib/validation";
import { ServiceError } from "../errors";
import { nextId, readStore, resetStore, updateStore } from "./mockStore";

const LATENCY_MS = 250;

function respond(compute) {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      try {
        resolve(structuredClone(compute()));
      } catch (error) {
        reject(error);
      }
    }, LATENCY_MS);
  });
}

function requireSupervisor(ctx) {
  if (ctx?.profile?.role !== "supervisor") {
    throw new ServiceError("Only supervisors can manage events.", { status: 403 });
  }
}

function requirePeerEducator(ctx) {
  if (ctx?.profile?.role !== "peer_educator") {
    throw new ServiceError("Only peer educators can register for shifts.", { status: 403 });
  }
}

function notFound(what) {
  return new ServiceError(`${what} not found.`, { status: 404 });
}

function activeCounts(store) {
  const counts = new Map();
  for (const registration of store.registrations) {
    if (registration.status === "active") {
      counts.set(registration.shift_id, (counts.get(registration.shift_id) ?? 0) + 1);
    }
  }
  return counts;
}

function shiftsFor(store, eventId) {
  return store.shifts.filter((shift) => shift.event_id === eventId).sort(compareShifts);
}

function summarizeEvent(store, event, counts, now) {
  const shifts = shiftsFor(store, event.event_id);
  const upcoming = shifts.some((shift) => !hasShiftEnded(shift, now));
  let activeRegistrations = 0;
  let totalCapacity = 0;
  let understaffed = 0;
  for (const shift of shifts) {
    const active = counts.get(shift.shift_id) ?? 0;
    activeRegistrations += active;
    totalCapacity += shift.capacity;
    if (active < shift.capacity) understaffed += 1;
  }
  const nextShift = shifts.find((shift) => !hasShiftEnded(shift, now));
  return {
    event_id: event.event_id,
    title: event.title,
    description: event.description,
    is_urgent: event.is_urgent,
    status: event.status,
    schedule_status: upcoming ? "upcoming" : "past",
    first_shift_date: shifts[0]?.shift_date ?? null,
    last_shift_date: shifts.at(-1)?.shift_date ?? null,
    next_shift_date: nextShift?.shift_date ?? null,
    shift_count: shifts.length,
    active_registrations: activeRegistrations,
    total_capacity: totalCapacity,
    understaffed_shifts: understaffed,
    created_at: event.created_at,
    updated_at: event.updated_at,
    cancelled_at: event.cancelled_at,
  };
}

function matchesStatus(summary, status) {
  if (status === "cancelled") return summary.status === "cancelled";
  if (status === "upcoming" || status === "past") {
    return summary.status !== "cancelled" && summary.schedule_status === status;
  }
  return true;
}

function eventDetail(store, eventId) {
  const event = store.events.find((item) => item.event_id === eventId);
  if (!event) throw notFound("Event");
  const counts = activeCounts(store);
  const locations = new Map(store.locations.map((location) => [location.location_id, location]));
  const organizer = store.users.find((user) => user.user_id === event.organizer_id);
  const shifts = shiftsFor(store, eventId);
  const shiftIds = new Set(shifts.map((shift) => shift.shift_id));

  return {
    ...summarizeEvent(store, event, counts, campusNow()),
    organizer: organizer ? { user_id: organizer.user_id, name: organizer.name } : null,
    has_registration_history: store.registrations.some((r) => shiftIds.has(r.shift_id)),
    shifts: shifts.map((shift) => {
      const active = counts.get(shift.shift_id) ?? 0;
      return {
        shift_id: shift.shift_id,
        shift_date: shift.shift_date,
        start_time: shift.start_time,
        end_time: shift.end_time,
        capacity: shift.capacity,
        location_id: shift.location_id,
        location: locations.get(shift.location_id) ?? null,
        active_registrations: active,
        remaining_spots: Math.max(shift.capacity - active, 0),
      };
    }),
  };
}

function toEventId(id) {
  const eventId = Number(id);
  return Number.isInteger(eventId) ? eventId : NaN;
}

function cleanEventInput(input) {
  return {
    title: normalizeText(input.title),
    description: (input.description ?? "").trim(),
    is_urgent: Boolean(input.is_urgent),
    shifts: (input.shifts ?? []).map((shift) => ({
      shift_id: shift.shift_id ?? null,
      shift_date: shift.shift_date,
      start_time: shift.start_time,
      end_time: shift.end_time,
      location_id: Number(shift.location_id),
      capacity: Number(shift.capacity),
    })),
  };
}

function assertValidEvent(store, input, lockedShifts = {}) {
  const errors = validateEventInput(input, {
    lockedShifts,
    locationIds: new Set(store.locations.map((location) => location.location_id)),
  });
  if (hasEventErrors(errors)) {
    throw new ServiceError("Please fix the highlighted fields.", { status: 422, fieldErrors: errors });
  }
}

function upsertUser(store, profile) {
  if (!store.users.some((user) => user.user_id === profile.user_id)) {
    store.users.push({
      user_id: profile.user_id,
      name: profile.name,
      email: profile.email,
      role: profile.role,
    });
  }
}

// ---------- Events ----------

export function getEvents({ search = "", status = "all", from, to } = {}, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    const store = readStore();
    const counts = activeCounts(store);
    const now = campusNow();
    const term = search.trim().toLowerCase();

    const results = store.events
      .filter((event) => !term || event.title.toLowerCase().includes(term))
      .filter((event) => {
        if (!from && !to) return true;
        return shiftsFor(store, event.event_id).some(
          (shift) => (!from || shift.shift_date >= from) && (!to || shift.shift_date <= to),
        );
      })
      .map((event) => summarizeEvent(store, event, counts, now))
      .filter((summary) => matchesStatus(summary, status));

    // Upcoming events first (soonest next shift), then everything else (most recent first).
    return results.sort((a, b) => {
      const aUpcoming = a.status !== "cancelled" && a.schedule_status === "upcoming";
      const bUpcoming = b.status !== "cancelled" && b.schedule_status === "upcoming";
      if (aUpcoming !== bUpcoming) return aUpcoming ? -1 : 1;
      if (aUpcoming) return (a.next_shift_date ?? "").localeCompare(b.next_shift_date ?? "");
      return (b.last_shift_date ?? "").localeCompare(a.last_shift_date ?? "");
    });
  });
}

export function getEvent(id, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    return eventDetail(readStore(), toEventId(id));
  });
}

export function createEvent(input, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    const cleaned = cleanEventInput(input);
    cleaned.shifts.forEach((shift) => (shift.shift_id = null));
    const eventId = updateStore((store) => {
      assertValidEvent(store, cleaned);
      upsertUser(store, ctx.profile);
      const now = new Date().toISOString();
      const event_id = nextId(store.events, "event_id");
      store.events.push({
        event_id,
        title: cleaned.title,
        description: cleaned.description,
        is_urgent: cleaned.is_urgent,
        status: "published",
        organizer_id: ctx.profile.user_id,
        created_at: now,
        updated_at: now,
        cancelled_at: null,
      });
      for (const shift of cleaned.shifts) {
        store.shifts.push({ ...shift, shift_id: nextId(store.shifts, "shift_id"), event_id });
      }
      return event_id;
    });
    return eventDetail(readStore(), eventId);
  });
}

export function updateEvent(id, input, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    const eventId = toEventId(id);
    const cleaned = cleanEventInput(input);
    updateStore((store) => {
      const event = store.events.find((item) => item.event_id === eventId);
      if (!event) throw notFound("Event");
      if (event.status === "cancelled") {
        throw new ServiceError("Cancelled events can't be edited.", { status: 409 });
      }

      const counts = activeCounts(store);
      const existing = shiftsFor(store, eventId);
      const lockedShifts = Object.fromEntries(
        existing.map((shift) => [
          shift.shift_id,
          { ...shift, active_registrations: counts.get(shift.shift_id) ?? 0 },
        ]),
      );

      for (const shift of cleaned.shifts) {
        if (shift.shift_id != null && !lockedShifts[shift.shift_id]) {
          throw new ServiceError("One of the shifts doesn't belong to this event.", { status: 422 });
        }
      }
      const keptIds = new Set(cleaned.shifts.map((shift) => shift.shift_id).filter(Boolean));
      const removed = existing.filter((shift) => !keptIds.has(shift.shift_id));
      if (removed.some((shift) => lockedShifts[shift.shift_id].active_registrations > 0)) {
        throw new ServiceError("Shifts with active registrations can't be removed.", { status: 409 });
      }

      assertValidEvent(store, cleaned, lockedShifts);

      Object.assign(event, {
        title: cleaned.title,
        description: cleaned.description,
        is_urgent: cleaned.is_urgent,
        updated_at: new Date().toISOString(),
      });

      const removedIds = new Set(removed.map((shift) => shift.shift_id));
      store.shifts = store.shifts.filter((shift) => !removedIds.has(shift.shift_id));
      store.registrations = store.registrations.filter((r) => !removedIds.has(r.shift_id));

      for (const shift of cleaned.shifts) {
        if (shift.shift_id != null) {
          Object.assign(
            store.shifts.find((item) => item.shift_id === shift.shift_id),
            shift,
          );
        } else {
          store.shifts.push({ ...shift, shift_id: nextId(store.shifts, "shift_id"), event_id: eventId });
        }
      }
    });
    return eventDetail(readStore(), eventId);
  });
}

export function cancelEvent(id, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    const eventId = toEventId(id);
    updateStore((store) => {
      const event = store.events.find((item) => item.event_id === eventId);
      if (!event) throw notFound("Event");
      if (event.status !== "cancelled") {
        const now = new Date().toISOString();
        Object.assign(event, { status: "cancelled", cancelled_at: now, updated_at: now });
      }
    });
    return eventDetail(readStore(), eventId);
  });
}

export function deleteDraftEvent(id, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    const eventId = toEventId(id);
    updateStore((store) => {
      const event = store.events.find((item) => item.event_id === eventId);
      if (!event) throw notFound("Event");
      const shiftIds = new Set(shiftsFor(store, eventId).map((shift) => shift.shift_id));
      const hasHistory = store.registrations.some((r) => shiftIds.has(r.shift_id));
      if (event.status !== "draft" || hasHistory) {
        throw new ServiceError("Only draft events with no registration history can be deleted.", {
          status: 409,
        });
      }
      store.events = store.events.filter((item) => item.event_id !== eventId);
      store.shifts = store.shifts.filter((shift) => shift.event_id !== eventId);
    });
    return null;
  });
}

export function getParticipants(id, { shiftId } = {}, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    const store = readStore();
    const eventId = toEventId(id);
    if (!store.events.some((event) => event.event_id === eventId)) throw notFound("Event");
    const shifts = new Map(shiftsFor(store, eventId).map((shift) => [shift.shift_id, shift]));
    const users = new Map(store.users.map((user) => [user.user_id, user]));

    return store.registrations
      .filter((r) => r.status === "active" && shifts.has(r.shift_id))
      .filter((r) => shiftId == null || r.shift_id === Number(shiftId))
      .map((r) => {
        const shift = shifts.get(r.shift_id);
        const user = users.get(r.user_id);
        return {
          registration_id: r.registration_id,
          registered_at: r.created_at,
          user: { user_id: r.user_id, name: user?.name ?? "Unknown user", email: user?.email ?? "" },
          shift: {
            shift_id: shift.shift_id,
            shift_date: shift.shift_date,
            start_time: shift.start_time,
            end_time: shift.end_time,
          },
        };
      })
      .sort((a, b) => compareShifts(a.shift, b.shift) || a.user.name.localeCompare(b.user.name));
  });
}

// ---------- Locations ----------

function locationsWithUsage(store) {
  const usage = new Map();
  for (const shift of store.shifts) {
    usage.set(shift.location_id, (usage.get(shift.location_id) ?? 0) + 1);
  }
  return store.locations
    .map((location) => ({ ...location, shift_count: usage.get(location.location_id) ?? 0 }))
    .sort(
      (a, b) => a.building.localeCompare(b.building) || a.room_or_area.localeCompare(b.room_or_area),
    );
}

function assertValidLocation(store, input, currentId = null) {
  const errors = validateLocation(input, store.locations, currentId);
  if (Object.keys(errors).length > 0) {
    const duplicate = errors.room_or_area?.startsWith("A location with this");
    throw new ServiceError(duplicate ? errors.room_or_area : "Please fix the highlighted fields.", {
      status: duplicate ? 409 : 422,
      fieldErrors: errors,
    });
  }
}

export function getLocations({ search = "" } = {}, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    const term = search.trim().toLowerCase();
    return locationsWithUsage(readStore()).filter(
      (location) =>
        !term ||
        location.building.toLowerCase().includes(term) ||
        location.room_or_area.toLowerCase().includes(term),
    );
  });
}

export function createLocation(input, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    const cleaned = cleanLocationInput(input);
    const locationId = updateStore((store) => {
      assertValidLocation(store, cleaned);
      const location_id = nextId(store.locations, "location_id");
      store.locations.push({ location_id, ...cleaned });
      return location_id;
    });
    return locationsWithUsage(readStore()).find((location) => location.location_id === locationId);
  });
}

export function updateLocation(id, input, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    const locationId = Number(id);
    const cleaned = cleanLocationInput(input);
    updateStore((store) => {
      const location = store.locations.find((item) => item.location_id === locationId);
      if (!location) throw notFound("Location");
      assertValidLocation(store, cleaned, locationId);
      Object.assign(location, cleaned);
    });
    return locationsWithUsage(readStore()).find((location) => location.location_id === locationId);
  });
}

// ---------- Reports ----------

export function getReport({ from, to } = {}, ctx) {
  return respond(() => {
    requireSupervisor(ctx);
    if (!isValidDateString(from) || !isValidDateString(to) || from > to) {
      throw new ServiceError("Choose a valid date range.", { status: 422 });
    }
    const store = readStore();
    const counts = activeCounts(store);
    // Only published events count toward staffing; cancelled and draft events are excluded.
    const events = new Map(
      store.events.filter((event) => event.status === "published").map((e) => [e.event_id, e]),
    );
    const shifts = store.shifts
      .filter((shift) => events.has(shift.event_id))
      .filter((shift) => shift.shift_date >= from && shift.shift_date <= to)
      .sort(compareShifts);
    const shiftIds = new Set(shifts.map((shift) => shift.shift_id));

    const rowsByEvent = new Map();
    let activeTotal = 0;
    let capacityTotal = 0;
    let openSpots = 0;
    let understaffed = 0;

    for (const shift of shifts) {
      const active = counts.get(shift.shift_id) ?? 0;
      const open = Math.max(shift.capacity - active, 0);
      activeTotal += active;
      capacityTotal += shift.capacity;
      openSpots += open;
      if (active < shift.capacity) understaffed += 1;

      if (!rowsByEvent.has(shift.event_id)) {
        rowsByEvent.set(shift.event_id, {
          event_id: shift.event_id,
          title: events.get(shift.event_id).title,
          first_shift_date: shift.shift_date,
          shifts_in_range: 0,
          active_registrations: 0,
          capacity: 0,
          open_spots: 0,
        });
      }
      const row = rowsByEvent.get(shift.event_id);
      row.shifts_in_range += 1;
      row.active_registrations += active;
      row.capacity += shift.capacity;
      row.open_spots += open;
    }

    const educators = new Set(
      store.registrations
        .filter((r) => r.status === "active" && shiftIds.has(r.shift_id))
        .map((r) => r.user_id),
    );
    const fillRate = (active, capacity) => (capacity > 0 ? (active / capacity) * 100 : null);

    return {
      range: { from, to },
      summary: {
        events_scheduled: rowsByEvent.size,
        active_registrations: activeTotal,
        unique_peer_educators: educators.size,
        open_spots: openSpots,
        total_capacity: capacityTotal,
        fill_rate: fillRate(activeTotal, capacityTotal),
        understaffed_shifts: understaffed,
      },
      rows: [...rowsByEvent.values()].map((row) => ({
        ...row,
        fill_rate: fillRate(row.active_registrations, row.capacity),
      })),
    };
  });
}

// ---------- Peer educators ----------
// Proposed rule (needs team confirmation): registration and cancellation close
// when a shift starts.

function locationLabel(location) {
  return location ? `${location.building} · ${location.room_or_area}` : null;
}

function locationById(store) {
  return new Map(store.locations.map((location) => [location.location_id, location]));
}

// The user's active registrations on events that aren't cancelled. Registrations
// on cancelled events stay as history but never block new sign-ups.
function myActiveRegistrations(store, userId) {
  const events = new Map(store.events.map((event) => [event.event_id, event]));
  const shifts = new Map(store.shifts.map((shift) => [shift.shift_id, shift]));
  return store.registrations
    .filter((r) => r.user_id === userId && r.status === "active")
    .map((registration) => {
      const shift = shifts.get(registration.shift_id);
      return { registration, shift, event: shift && events.get(shift.event_id) };
    })
    .filter((item) => item.shift && item.event && item.event.status !== "cancelled");
}

// Single source of truth for whether a user may register for a shift. The
// register mutation runs it again, so a stale page can't bypass the rules.
function shiftEligibility({ event, shift, counts, mine, now }) {
  const own = mine.find((item) => item.shift.shift_id === shift.shift_id);
  if (own) return { code: "registered", registration_id: own.registration.registration_id };
  if (event.status === "cancelled") return { code: "event_cancelled" };
  if (event.status !== "published" || hasShiftStarted(shift, now)) return { code: "closed" };
  if (mine.some((item) => item.event.event_id === event.event_id)) {
    return { code: "registered_other_shift" };
  }
  if ((counts.get(shift.shift_id) ?? 0) >= shift.capacity) return { code: "full" };
  const conflict = mine.find((item) => shiftsOverlap(shift, item.shift));
  if (conflict) {
    return {
      code: "conflict",
      conflict: {
        event_id: conflict.event.event_id,
        title: conflict.event.title,
        shift_date: conflict.shift.shift_date,
        start_time: conflict.shift.start_time,
        end_time: conflict.shift.end_time,
      },
    };
  }
  return { code: "open" };
}

function eligibilityError(eligibility) {
  const messages = {
    registered: "You're already registered for this shift.",
    registered_other_shift:
      "You're already registered for another shift in this event. Cancel that registration first to switch shifts.",
    full: "This shift is full.",
    event_cancelled: "This event was cancelled, so registration is closed.",
    closed: "Registration for this shift is closed because it has already started.",
  };
  const c = eligibility.conflict;
  const message =
    eligibility.code === "conflict"
      ? `This shift overlaps your registration for ${c.title} on ${formatDate(c.shift_date)}, ${formatTimeRange(c.start_time, c.end_time)}.`
      : messages[eligibility.code];
  return new ServiceError(message, { status: 409, code: eligibility.code });
}

function educatorEventSummary(store, event, counts, mine, now) {
  const shifts = shiftsFor(store, event.event_id);
  const openable = shifts.filter((shift) => !hasShiftStarted(shift, now));
  const locations = locationById(store);
  let remaining = 0;
  let openShifts = 0;
  for (const shift of openable) {
    const spots = Math.max(shift.capacity - (counts.get(shift.shift_id) ?? 0), 0);
    remaining += spots;
    if (spots > 0) openShifts += 1;
  }
  const locationIds = new Set((openable.length ? openable : shifts).map((s) => s.location_id));
  const mineHere = mine.find((item) => item.event.event_id === event.event_id);

  return {
    event_id: event.event_id,
    title: event.title,
    description: event.description,
    is_urgent: event.is_urgent,
    status: event.status,
    upcoming_shift_count: openable.length,
    open_shift_count: openShifts,
    remaining_spots: remaining,
    next_shift_date: openable[0]?.shift_date ?? null,
    next_shift_start_time: openable[0]?.start_time ?? null,
    last_shift_date: shifts.at(-1)?.shift_date ?? null,
    location_summary:
      locationIds.size > 1
        ? "Multiple locations"
        : locationLabel(locations.get([...locationIds][0])),
    my_registration: mineHere
      ? {
          registration_id: mineHere.registration.registration_id,
          shift_id: mineHere.shift.shift_id,
          shift_date: mineHere.shift.shift_date,
          start_time: mineHere.shift.start_time,
          end_time: mineHere.shift.end_time,
        }
      : null,
  };
}

// Published events with at least one shift that hasn't started yet.
// availability: "all" | "open" (only events with a remaining spot).
export function getAvailableEvents({ search = "", from, to, availability = "all" } = {}, ctx) {
  return respond(() => {
    requirePeerEducator(ctx);
    const store = readStore();
    const counts = activeCounts(store);
    const now = campusNow();
    const mine = myActiveRegistrations(store, ctx.profile.user_id);
    const term = search.trim().toLowerCase();

    return store.events
      .filter((event) => event.status === "published")
      .filter((event) => !term || event.title.toLowerCase().includes(term))
      .filter((event) => {
        if (!from && !to) return true;
        return shiftsFor(store, event.event_id).some(
          (shift) =>
            !hasShiftStarted(shift, now) &&
            (!from || shift.shift_date >= from) &&
            (!to || shift.shift_date <= to),
        );
      })
      .map((event) => educatorEventSummary(store, event, counts, mine, now))
      .filter((summary) => summary.upcoming_shift_count > 0)
      .filter((summary) => availability !== "open" || summary.open_shift_count > 0)
      .sort(
        (a, b) =>
          a.next_shift_date.localeCompare(b.next_shift_date) ||
          a.next_shift_start_time.localeCompare(b.next_shift_start_time) ||
          a.title.localeCompare(b.title),
      );
  });
}

export function getEducatorEvent(id, ctx) {
  return respond(() => {
    requirePeerEducator(ctx);
    const store = readStore();
    const eventId = toEventId(id);
    const event = store.events.find((item) => item.event_id === eventId);
    // Drafts aren't visible to peer educators.
    if (!event || event.status === "draft") throw notFound("Event");

    const counts = activeCounts(store);
    const now = campusNow();
    const locations = locationById(store);
    const userId = ctx.profile.user_id;
    const mine = myActiveRegistrations(store, userId);
    const shifts = shiftsFor(store, eventId);
    const shiftIds = new Set(shifts.map((shift) => shift.shift_id));
    const myRegistration = store.registrations.find(
      (r) => r.user_id === userId && r.status === "active" && shiftIds.has(r.shift_id),
    );

    return {
      event_id: event.event_id,
      title: event.title,
      description: event.description,
      is_urgent: event.is_urgent,
      status: event.status,
      cancelled_at: event.cancelled_at,
      schedule_status: shifts.some((shift) => !hasShiftEnded(shift, now)) ? "upcoming" : "past",
      first_shift_date: shifts[0]?.shift_date ?? null,
      last_shift_date: shifts.at(-1)?.shift_date ?? null,
      my_registration: myRegistration
        ? { registration_id: myRegistration.registration_id, shift_id: myRegistration.shift_id }
        : null,
      shifts: shifts.map((shift) => {
        const active = counts.get(shift.shift_id) ?? 0;
        return {
          shift_id: shift.shift_id,
          shift_date: shift.shift_date,
          start_time: shift.start_time,
          end_time: shift.end_time,
          capacity: shift.capacity,
          location: locations.get(shift.location_id) ?? null,
          active_registrations: active,
          remaining_spots: Math.max(shift.capacity - active, 0),
          has_started: hasShiftStarted(shift, now),
          has_ended: hasShiftEnded(shift, now),
          eligibility: shiftEligibility({ event, shift, counts, mine, now }),
        };
      }),
    };
  });
}

export function registerForShift(shiftId, ctx) {
  return respond(() => {
    requirePeerEducator(ctx);
    const userId = ctx.profile.user_id;
    const registrationId = updateStore((store) => {
      const shift = store.shifts.find((item) => item.shift_id === Number(shiftId));
      const event = shift && store.events.find((item) => item.event_id === shift.event_id);
      if (!shift || !event || event.status === "draft") throw notFound("Shift");

      const eligibility = shiftEligibility({
        event,
        shift,
        counts: activeCounts(store),
        mine: myActiveRegistrations(store, userId),
        now: campusNow(),
      });
      if (eligibility.code !== "open") throw eligibilityError(eligibility);

      upsertUser(store, ctx.profile);
      const registration_id = nextId(store.registrations, "registration_id");
      // Always a new record: a cancelled registration is never reactivated.
      store.registrations.push({
        registration_id,
        shift_id: shift.shift_id,
        user_id: userId,
        status: "active",
        created_at: new Date().toISOString(),
        cancelled_at: null,
      });
      return registration_id;
    });
    return registrationDetail(readStore(), registrationId);
  });
}

export function cancelRegistration(registrationId, ctx) {
  return respond(() => {
    requirePeerEducator(ctx);
    const id = Number(registrationId);
    updateStore((store) => {
      const registration = store.registrations.find((r) => r.registration_id === id);
      if (!registration || registration.user_id !== ctx.profile.user_id) {
        throw notFound("Registration");
      }
      if (registration.status !== "active") {
        throw new ServiceError("This registration is already cancelled.", { status: 409 });
      }
      const shift = store.shifts.find((item) => item.shift_id === registration.shift_id);
      const event = store.events.find((item) => item.event_id === shift.event_id);
      if (event.status === "cancelled") {
        throw new ServiceError("This event was cancelled, so there's nothing to cancel.", {
          status: 409,
        });
      }
      if (hasShiftStarted(shift, campusNow())) {
        throw new ServiceError("This shift has already started, so it can't be cancelled here.", {
          status: 409,
        });
      }
      Object.assign(registration, { status: "cancelled", cancelled_at: new Date().toISOString() });
    });
    return registrationDetail(readStore(), id);
  });
}

function registrationDetail(store, registrationId, now = campusNow()) {
  const registration = store.registrations.find((r) => r.registration_id === registrationId);
  const shift = store.shifts.find((item) => item.shift_id === registration.shift_id);
  const event = store.events.find((item) => item.event_id === shift.event_id);
  const location = store.locations.find((item) => item.location_id === shift.location_id) ?? null;

  let category;
  if (registration.status === "cancelled") category = "cancelled_by_user";
  else if (event.status === "cancelled") category = "event_cancelled";
  else if (hasShiftEnded(shift, now)) category = "past";
  else if (hasShiftStarted(shift, now)) category = "in_progress";
  else category = "upcoming";

  return {
    registration_id: registration.registration_id,
    status: registration.status,
    category,
    can_cancel: category === "upcoming",
    created_at: registration.created_at,
    cancelled_at: registration.cancelled_at ?? null,
    event: {
      event_id: event.event_id,
      title: event.title,
      status: event.status,
      is_urgent: event.is_urgent,
      cancelled_at: event.cancelled_at,
    },
    shift: {
      shift_id: shift.shift_id,
      shift_date: shift.shift_date,
      start_time: shift.start_time,
      end_time: shift.end_time,
    },
    location,
    attendance: attendanceFor(store, registration.registration_id),
  };
}

function attendanceFor(store, registrationId) {
  const record = (store.attendance ?? []).find((a) => a.registration_id === registrationId);
  return record
    ? {
        attendance_id: record.attendance_id,
        participation_status: record.participation_status,
        credited_minutes: record.credited_minutes,
      }
    : null;
}

// Every registration the user has made, active or cancelled, oldest shift first.
export function getMyRegistrations(_filters, ctx) {
  return respond(() => {
    requirePeerEducator(ctx);
    const store = readStore();
    const now = campusNow();
    return store.registrations
      .filter((r) => r.user_id === ctx.profile.user_id)
      .map((r) => registrationDetail(store, r.registration_id, now))
      .sort(
        (a, b) =>
          compareShifts(a.shift, b.shift) || a.created_at.localeCompare(b.created_at),
      );
  });
}

// ---------- Attendance ----------
// Same rules as backend/app/routes/attendance.py.

function minutesBetween(start, end) {
  const [startHour, startMinute] = start.split(":").map(Number);
  const [endHour, endMinute] = end.split(":").map(Number);
  return endHour * 60 + endMinute - (startHour * 60 + startMinute);
}

function requireSupervisorTo(ctx, action) {
  if (ctx?.profile?.role !== "supervisor") {
    throw new ServiceError(`Only supervisors can ${action}`, { status: 403 });
  }
}

function attendanceBlockedReason(event, shift, now) {
  if (event.status === "cancelled") return "This event was cancelled, so attendance can't be changed.";
  if (event.status !== "published") return "Attendance can only be recorded for published events.";
  if (!hasShiftStarted(shift, now)) return "Attendance can be recorded once the shift starts.";
  return null;
}

function shiftRoster(store, shiftId, now) {
  const shift = store.shifts.find((item) => item.shift_id === shiftId);
  if (!shift) throw notFound("Shift");
  const event = store.events.find((item) => item.event_id === shift.event_id);
  const location = store.locations.find((item) => item.location_id === shift.location_id) ?? null;
  const users = new Map(store.users.map((user) => [user.user_id, user]));
  const records = new Map((store.attendance ?? []).map((record) => [record.registration_id, record]));

  const roster = store.registrations
    .filter((r) => r.shift_id === shiftId && r.status === "active")
    .map((r) => {
      const user = users.get(r.user_id);
      const record = records.get(r.registration_id);
      return {
        registration_id: r.registration_id,
        registered_at: r.created_at,
        user: { user_id: r.user_id, name: user?.name ?? "Unknown user", email: user?.email ?? "" },
        attendance: record
          ? {
              attendance_id: record.attendance_id,
              participation_status: record.participation_status,
              credited_minutes: record.credited_minutes,
            }
          : null,
      };
    })
    .sort((a, b) => a.user.name.localeCompare(b.user.name));

  const marked = roster.map((entry) => entry.attendance).filter(Boolean);
  const blocked = attendanceBlockedReason(event, shift, now);
  return {
    shift: {
      shift_id: shift.shift_id,
      shift_date: shift.shift_date,
      start_time: shift.start_time,
      end_time: shift.end_time,
      capacity: shift.capacity,
      duration_minutes: minutesBetween(shift.start_time, shift.end_time),
      has_started: hasShiftStarted(shift, now),
      has_ended: hasShiftEnded(shift, now),
      location,
    },
    event: { event_id: event.event_id, title: event.title, status: event.status },
    can_record: blocked === null,
    blocked_reason: blocked,
    summary: {
      registered: roster.length,
      attended: marked.filter((a) => a.participation_status === "attended").length,
      absent: marked.filter((a) => a.participation_status === "absent").length,
      unmarked: roster.length - marked.length,
      credited_minutes: marked.reduce((sum, a) => sum + a.credited_minutes, 0),
    },
    roster,
  };
}

function cleanAttendanceRecord(record, maxMinutes) {
  const errors = {};
  const status =
    typeof record.participation_status === "string" ? record.participation_status.trim().toLowerCase() : null;
  if (status !== "attended" && status !== "absent") errors.participation_status = 'Choose "attended" or "absent".';

  const raw = record.credited_minutes;
  const given = raw !== undefined && raw !== null && String(raw).trim() !== "";
  let minutes = given && /^[0-9]{1,18}$/.test(String(raw).trim()) ? Number(String(raw).trim()) : null;
  if (given && minutes === null) errors.credited_minutes = "Enter a whole number of minutes, 0 or more.";
  else if (minutes !== null && minutes > maxMinutes)
    errors.credited_minutes = `Credited minutes can't be more than the shift's ${maxMinutes} minutes.`;
  else if (status === "absent" && minutes) errors.credited_minutes = "Absent participants can't be credited minutes.";

  if (status === "absent") minutes = 0;
  else if (minutes === null) minutes = maxMinutes;
  return { cleaned: { participation_status: status, credited_minutes: minutes }, errors };
}

export function getShiftAttendance(shiftId, ctx) {
  return respond(() => {
    requireSupervisorTo(ctx, "view attendance");
    return shiftRoster(readStore(), Number(shiftId), campusNow());
  });
}

export function saveShiftAttendance(shiftId, records, ctx) {
  return respond(() => {
    requireSupervisorTo(ctx, "record attendance");
    const id = Number(shiftId);
    const now = campusNow();
    const roster = shiftRoster(readStore(), id, now);
    if (!roster.can_record) throw new ServiceError(roster.blocked_reason, { status: 409 });
    if (!Array.isArray(records) || records.length === 0) {
      throw new ServiceError("Add at least one attendance record.", {
        status: 422,
        fieldErrors: { records: "Add at least one attendance record." },
      });
    }

    const active = new Set(roster.roster.map((entry) => entry.registration_id));
    const onShift = new Set(readStore().registrations.filter((r) => r.shift_id === id).map((r) => r.registration_id));
    const seen = new Set();
    const cleaned = [];
    const recordErrors = {};
    records.forEach((record, index) => {
      const { cleaned: values, errors } = cleanAttendanceRecord(record, roster.shift.duration_minutes);
      const registrationId = Number(record.registration_id);
      if (!onShift.has(registrationId)) errors.registration_id = "This registration isn't on this shift.";
      else if (seen.has(registrationId)) errors.registration_id = "This registration is listed more than once.";
      else if (!active.has(registrationId)) errors.registration_id = "Cancelled registrations can't have attendance.";
      seen.add(registrationId);
      if (Object.keys(errors).length > 0) recordErrors[String(index)] = errors;
      cleaned.push({ registration_id: registrationId, ...values });
    });
    if (Object.keys(recordErrors).length > 0) {
      throw new ServiceError("Please fix the highlighted fields.", {
        status: 422,
        fieldErrors: { records: recordErrors },
      });
    }

    updateStore((store) => {
      store.attendance = store.attendance ?? [];
      for (const values of cleaned) {
        const existing = store.attendance.find((a) => a.registration_id === values.registration_id);
        if (existing) Object.assign(existing, values);
        else store.attendance.push({ attendance_id: nextId(store.attendance, "attendance_id"), ...values });
      }
    });
    return shiftRoster(readStore(), id, now);
  });
}

export function clearAttendance(registrationId, ctx) {
  return respond(() => {
    requireSupervisorTo(ctx, "record attendance");
    const store = readStore();
    const id = Number(registrationId);
    const registration = store.registrations.find((r) => r.registration_id === id);
    if (!registration) throw notFound("Registration");
    const shift = store.shifts.find((item) => item.shift_id === registration.shift_id);
    const event = store.events.find((item) => item.event_id === shift.event_id);
    if (event.status === "cancelled") {
      throw new ServiceError("This event was cancelled, so attendance can't be changed.", { status: 409 });
    }
    updateStore((draft) => {
      draft.attendance = (draft.attendance ?? []).filter((a) => a.registration_id !== id);
    });
    return null;
  });
}

export function getAttendanceSummary({ from, to } = {}, ctx) {
  return respond(() => {
    if (ctx?.profile?.role !== "supervisor") {
      throw new ServiceError("Only supervisors can view attendance", { status: 403 });
    }
    if (!isValidDateString(from) || !isValidDateString(to) || from > to) {
      throw new ServiceError("Choose a valid date range.", { status: 422 });
    }
    const store = readStore();
    const registrations = new Map(store.registrations.map((r) => [r.registration_id, r]));
    const shifts = new Map(store.shifts.map((shift) => [shift.shift_id, shift]));
    const users = new Map(store.users.map((user) => [user.user_id, user]));
    const byUser = new Map();
    for (const record of store.attendance ?? []) {
      const registration = registrations.get(record.registration_id);
      const shift = registration && shifts.get(registration.shift_id);
      if (!shift || shift.shift_date < from || shift.shift_date > to) continue;
      const row = byUser.get(registration.user_id) ?? {
        user: {
          user_id: registration.user_id,
          name: users.get(registration.user_id)?.name ?? "Unknown user",
          email: users.get(registration.user_id)?.email ?? "",
        },
        shifts_attended: 0,
        shifts_absent: 0,
        credited_minutes: 0,
      };
      if (record.participation_status === "attended") row.shifts_attended += 1;
      else row.shifts_absent += 1;
      row.credited_minutes += record.credited_minutes;
      byUser.set(registration.user_id, row);
    }
    const rows = [...byUser.values()].sort(
      (a, b) => b.credited_minutes - a.credited_minutes || a.user.name.localeCompare(b.user.name),
    );
    return {
      range: { from, to },
      totals: {
        peer_educators: rows.length,
        shifts_attended: rows.reduce((sum, row) => sum + row.shifts_attended, 0),
        shifts_absent: rows.reduce((sum, row) => sum + row.shifts_absent, 0),
        credited_minutes: rows.reduce((sum, row) => sum + row.credited_minutes, 0),
      },
      rows,
    };
  });
}

export function getMyAttendance(ctx) {
  return respond(() => {
    if (ctx?.profile?.role !== "peer_educator") {
      throw new ServiceError("Only peer educators can view their participation history", { status: 403 });
    }
    const store = readStore();
    const registrations = new Map(store.registrations.map((r) => [r.registration_id, r]));
    const records = (store.attendance ?? [])
      .map((record) => {
        const registration = registrations.get(record.registration_id);
        if (!registration || registration.user_id !== ctx.profile.user_id) return null;
        const shift = store.shifts.find((item) => item.shift_id === registration.shift_id);
        const event = store.events.find((item) => item.event_id === shift.event_id);
        return {
          attendance_id: record.attendance_id,
          registration_id: record.registration_id,
          participation_status: record.participation_status,
          credited_minutes: record.credited_minutes,
          event: { event_id: event.event_id, title: event.title },
          shift: {
            shift_id: shift.shift_id,
            shift_date: shift.shift_date,
            start_time: shift.start_time,
            end_time: shift.end_time,
          },
          location: store.locations.find((item) => item.location_id === shift.location_id) ?? null,
        };
      })
      .filter(Boolean)
      .sort((a, b) => -compareShifts(a.shift, b.shift) || b.attendance_id - a.attendance_id);
    return {
      summary: {
        shifts_attended: records.filter((r) => r.participation_status === "attended").length,
        shifts_absent: records.filter((r) => r.participation_status === "absent").length,
        credited_minutes: records.reduce((sum, r) => sum + r.credited_minutes, 0),
      },
      records,
    };
  });
}

// ---------- People and roles ----------
// Same rules as backend/app/routes/users.py.

// Sign-ups for shifts that haven't started: the ones a peer educator can still cancel.
function upcomingRegistrationCount(store, userId, now) {
  const shifts = new Map(store.shifts.map((shift) => [shift.shift_id, shift]));
  const events = new Map(store.events.map((event) => [event.event_id, event]));
  return store.registrations.filter((r) => {
    if (r.user_id !== userId || r.status !== "active") return false;
    const shift = shifts.get(r.shift_id);
    return events.get(shift.event_id)?.status !== "cancelled" && !hasShiftStarted(shift, now);
  }).length;
}

export function getUsers({ search = "" } = {}, ctx) {
  return respond(() => {
    if (ctx?.profile?.role !== "supervisor") {
      throw new ServiceError("Only supervisors can view people", { status: 403 });
    }
    // The signed-in supervisor comes from the real /api/me, so add them to the demo people.
    if (ctx.profile.user_id && !readStore().users.some((user) => user.user_id === ctx.profile.user_id)) {
      updateStore((draft) => upsertUser(draft, ctx.profile));
    }
    const store = readStore();
    const now = campusNow();
    const term = normalizeText(search).toLowerCase();
    return store.users
      .filter((user) => !term || user.name.toLowerCase().includes(term) || user.email.toLowerCase().includes(term))
      .map((user) => ({
        user_id: user.user_id,
        name: user.name,
        email: user.email,
        role: user.role,
        upcoming_registrations: upcomingRegistrationCount(store, user.user_id, now),
        is_you: user.user_id === ctx.profile.user_id,
      }))
      .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()) || a.email.localeCompare(b.email));
  });
}

export function setUserRole(userId, role, ctx) {
  return respond(() => {
    if (ctx?.profile?.role !== "supervisor") {
      throw new ServiceError("Only supervisors can change roles.", { status: 403, code: "forbidden" });
    }
    const cleanRole = typeof role === "string" ? role.trim().toLowerCase() : null;
    if (cleanRole !== "supervisor" && cleanRole !== "peer_educator") {
      throw new ServiceError("Please fix the highlighted fields.", {
        status: 422,
        fieldErrors: { role: 'Choose "supervisor" or "peer_educator".' },
      });
    }
    if (userId === ctx.profile.user_id) {
      throw new ServiceError("You can't change your own role. Ask another supervisor to do it.", {
        status: 409,
        code: "own_role",
      });
    }
    const store = readStore();
    const target = store.users.find((user) => user.user_id === userId);
    if (!target) throw notFound("User");
    if (cleanRole === "supervisor" && target.role !== "supervisor") {
      const upcoming = upcomingRegistrationCount(store, userId, campusNow());
      if (upcoming) {
        throw new ServiceError(
          `${target.name || target.email} has ${upcoming} upcoming shift ${upcoming === 1 ? "registration" : "registrations"}. ` +
            "They need to cancel them before becoming a supervisor.",
          { status: 409, code: "has_registrations" },
        );
      }
    }
    updateStore((draft) => {
      draft.users.find((user) => user.user_id === userId).role = cleanRole;
    });
    return { user_id: target.user_id, name: target.name, email: target.email, role: cleanRole, is_you: false };
  });
}

// ---------- Demo only ----------

export function resetDemoData() {
  resetStore();
  return Promise.resolve();
}
