import DashboardLayout from "../supervisor/DashboardLayout";
import { CalendarCheckIcon, CompassIcon } from "../supervisor/Icons";
import "./educator.css";

const EVENTS_PATH = "/educator/events";

const NAV_ITEMS = [
  {
    to: EVENTS_PATH,
    label: "Explore",
    Icon: CompassIcon,
    isActive: (path) => path === EVENTS_PATH || path.startsWith(`${EVENTS_PATH}/`),
  },
  { to: "/educator/my-events", label: "My Events", Icon: CalendarCheckIcon },
];

export default function EducatorLayout() {
  return (
    <DashboardLayout
      homePath={EVENTS_PATH}
      searchPath={EVENTS_PATH}
      navItems={NAV_ITEMS}
      navLabel="Peer educator"
      roleLabel="Peer educator"
    />
  );
}
