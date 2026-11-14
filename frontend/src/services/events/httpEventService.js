// Client for the events API in API_CONTRACT.md. The supervisor endpoints exist
// in the backend; the peer educator ones don't yet. It is used when
// VITE_SUPERVISOR_DATA_SOURCE=api (supervisor screens) or
// VITE_EVENTS_DATA_SOURCE=api (everything), and it never falls back to demo data.
import { API_BASE_URL } from "../../lib/api";
import { ServiceError } from "../errors";

async function request(path, ctx, { method = "GET", query, body } = {}) {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }

  let response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${ctx.accessToken}`,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ServiceError(
      "We couldn't reach the Peer Connections server. Check your connection and try again.",
      { status: 0 },
    );
  }

  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof data?.detail === "string" ? data.detail : "The request failed. Please try again.";
    throw new ServiceError(message, {
      status: response.status,
      fieldErrors: data?.field_errors ?? null,
      code: data?.code ?? null,
    });
  }
  return data;
}

export const getEvents = (params, ctx) => request("/api/events", ctx, { query: params });
export const getEvent = (id, ctx) => request(`/api/events/${id}`, ctx);
export const createEvent = (input, ctx) => request("/api/events", ctx, { method: "POST", body: input });
export const updateEvent = (id, input, ctx) =>
  request(`/api/events/${id}`, ctx, { method: "PUT", body: input });
export const cancelEvent = (id, ctx) => request(`/api/events/${id}/cancel`, ctx, { method: "POST" });
export const deleteDraftEvent = (id, ctx) => request(`/api/events/${id}`, ctx, { method: "DELETE" });
export const getParticipants = (id, params, ctx) =>
  request(`/api/events/${id}/participants`, ctx, { query: { shift_id: params?.shiftId } });
export const getLocations = (params, ctx) => request("/api/locations", ctx, { query: params });
export const createLocation = (input, ctx) =>
  request("/api/locations", ctx, { method: "POST", body: input });
export const updateLocation = (id, input, ctx) =>
  request(`/api/locations/${id}`, ctx, { method: "PUT", body: input });
export const getReport = (params, ctx) => request("/api/reports/staffing", ctx, { query: params });

// Peer educator endpoints (proposed).
export const getAvailableEvents = (params, ctx) =>
  request("/api/educator/events", ctx, { query: params });
export const getEducatorEvent = (id, ctx) => request(`/api/educator/events/${id}`, ctx);
export const getMyRegistrations = (params, ctx) =>
  request("/api/me/registrations", ctx, { query: params });
export const registerForShift = (shiftId, ctx) =>
  request(`/api/shifts/${shiftId}/registrations`, ctx, { method: "POST" });
export const cancelRegistration = (registrationId, ctx) =>
  request(`/api/registrations/${registrationId}/cancel`, ctx, { method: "POST" });
