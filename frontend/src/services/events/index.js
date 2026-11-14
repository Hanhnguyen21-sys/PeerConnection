// Chooses the event data implementation.
// - VITE_SUPERVISOR_DATA_SOURCE=api: the supervisor dashboard (events,
//   participants, locations, reports) uses the backend; peer educator screens
//   stay on demo data until their endpoints exist.
// - VITE_EVENTS_DATA_SOURCE=api: everything uses the backend.
// Otherwise everything is demo data saved in the browser.
import * as demoService from "./mockEventService";
import * as apiService from "./httpEventService";

export const eventsDataSource = import.meta.env.VITE_EVENTS_DATA_SOURCE === "api" ? "api" : "demo";

export const supervisorDataSource =
  eventsDataSource === "api" || import.meta.env.VITE_SUPERVISOR_DATA_SOURCE === "api" ? "api" : "demo";

const SUPERVISOR_FUNCTIONS = [
  "getEvents",
  "getEvent",
  "createEvent",
  "updateEvent",
  "cancelEvent",
  "deleteDraftEvent",
  "getParticipants",
  "getLocations",
  "createLocation",
  "updateLocation",
  "getReport",
];

function demoWithApiSupervisor() {
  const service = { ...demoService };
  for (const name of SUPERVISOR_FUNCTIONS) service[name] = apiService[name];
  return service;
}

export const eventService =
  eventsDataSource === "api"
    ? apiService
    : supervisorDataSource === "api"
      ? demoWithApiSupervisor()
      : demoService;
