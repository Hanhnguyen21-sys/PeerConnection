import { useEffect, useMemo, useRef } from "react";
import { useAuth } from "../../auth/AuthContext";
import { eventService } from "./index";

// Binds the signed-in session to the event service so pages never handle
// tokens. The returned object is stable, so it is safe in effect dependencies.
export function useEventsApi() {
  const { session, profile } = useAuth();
  const ctxRef = useRef({ accessToken: session?.access_token ?? null, profile });

  useEffect(() => {
    ctxRef.current = { accessToken: session?.access_token ?? null, profile };
  }, [session, profile]);

  return useMemo(() => {
    const ctx = () => ctxRef.current;
    return {
      getEvents: (params) => eventService.getEvents(params, ctx()),
      getEvent: (id) => eventService.getEvent(id, ctx()),
      createEvent: (input) => eventService.createEvent(input, ctx()),
      updateEvent: (id, input) => eventService.updateEvent(id, input, ctx()),
      cancelEvent: (id) => eventService.cancelEvent(id, ctx()),
      deleteDraftEvent: (id) => eventService.deleteDraftEvent(id, ctx()),
      getParticipants: (id, params) => eventService.getParticipants(id, params, ctx()),
      getLocations: (params) => eventService.getLocations(params, ctx()),
      createLocation: (input) => eventService.createLocation(input, ctx()),
      updateLocation: (id, input) => eventService.updateLocation(id, input, ctx()),
      getReport: (params) => eventService.getReport(params, ctx()),
      getAvailableEvents: (params) => eventService.getAvailableEvents(params, ctx()),
      getEducatorEvent: (id) => eventService.getEducatorEvent(id, ctx()),
      getMyRegistrations: (params) => eventService.getMyRegistrations(params, ctx()),
      registerForShift: (shiftId) => eventService.registerForShift(shiftId, ctx()),
      cancelRegistration: (id) => eventService.cancelRegistration(id, ctx()),
    };
  }, []);
}
