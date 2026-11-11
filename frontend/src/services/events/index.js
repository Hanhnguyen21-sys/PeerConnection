// Chooses the event data implementation. Demo data is the default until the
// events API exists; set VITE_EVENTS_DATA_SOURCE=api to use the backend.
import * as demoService from "./mockEventService";
import * as apiService from "./httpEventService";

export const eventsDataSource = import.meta.env.VITE_EVENTS_DATA_SOURCE === "api" ? "api" : "demo";

export const eventService = eventsDataSource === "api" ? apiService : demoService;
