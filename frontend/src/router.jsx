import { createBrowserRouter, Navigate } from "react-router-dom";
import App from "./App";
import EducatorLayout from "./components/educator/EducatorLayout";
import { GuestOnly, RequireAuth, RequireRole, RootRoute } from "./components/RouteGuards";
import SupervisorLayout from "./components/supervisor/SupervisorLayout";
import SignIn from "./pages/SignIn";
import SignUp from "./pages/SignUp";

// Dashboard pages load on demand so the sign-in bundle stays small.
const page = (load) => async () => ({ Component: (await load()).default });

// A data router is required for useBlocker (unsaved-changes warnings).
export const router = createBrowserRouter([
  {
    element: <App />,
    children: [
      {
        path: "/",
        element: (
          <RequireAuth>
            <RootRoute />
          </RequireAuth>
        ),
      },
      {
        path: "/sign-in",
        element: (
          <GuestOnly>
            <SignIn />
          </GuestOnly>
        ),
      },
      {
        path: "/sign-up",
        element: (
          <GuestOnly>
            <SignUp />
          </GuestOnly>
        ),
      },
      {
        path: "/supervisor",
        element: (
          <RequireAuth>
            <RequireRole role="supervisor">
              <SupervisorLayout />
            </RequireRole>
          </RequireAuth>
        ),
        children: [
          { index: true, lazy: page(() => import("./pages/supervisor/EventsHome")) },
          { path: "events/new", lazy: page(() => import("./pages/supervisor/EventCreate")) },
          { path: "events/:eventId", lazy: page(() => import("./pages/supervisor/EventDetail")) },
          { path: "events/:eventId/edit", lazy: page(() => import("./pages/supervisor/EventEdit")) },
          { path: "reports", lazy: page(() => import("./pages/supervisor/Reports")) },
          { path: "locations", lazy: page(() => import("./pages/supervisor/Locations")) },
          { path: "*", lazy: page(() => import("./pages/supervisor/SupervisorNotFound")) },
        ],
      },
      {
        path: "/educator",
        element: (
          <RequireAuth>
            <RequireRole role="peer_educator">
              <EducatorLayout />
            </RequireRole>
          </RequireAuth>
        ),
        children: [
          { index: true, element: <Navigate to="events" replace /> },
          { path: "events", lazy: page(() => import("./pages/educator/ExploreEvents")) },
          { path: "events/:eventId", lazy: page(() => import("./pages/educator/EducatorEventDetail")) },
          { path: "my-events", lazy: page(() => import("./pages/educator/MyEvents")) },
          { path: "*", lazy: page(() => import("./pages/educator/EducatorNotFound")) },
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
