import DashboardLayout from "./DashboardLayout";
import { ChartIcon, HomeIcon, MapPinIcon, PlusCircleIcon, UsersIcon } from "./Icons";

const HOME_PATH = "/supervisor";

const NAV_ITEMS = [
  {
    to: HOME_PATH,
    label: "Home",
    Icon: HomeIcon,
    isActive: (path) =>
      path === HOME_PATH ||
      (path.startsWith(`${HOME_PATH}/events/`) && path !== `${HOME_PATH}/events/new`),
  },
  { to: `${HOME_PATH}/events/new`, label: "Create", Icon: PlusCircleIcon },
  { to: `${HOME_PATH}/reports`, label: "Reports", Icon: ChartIcon },
  { to: `${HOME_PATH}/locations`, label: "Locations", Icon: MapPinIcon },
  { to: `${HOME_PATH}/people`, label: "People", Icon: UsersIcon },
];

export default function SupervisorLayout() {
  return (
    <DashboardLayout
      homePath={HOME_PATH}
      searchPath={HOME_PATH}
      navItems={NAV_ITEMS}
      navLabel="Supervisor"
      roleLabel="Supervisor"
    />
  );
}
