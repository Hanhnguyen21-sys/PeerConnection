import { useState } from "react";
import { ExternalLinkIcon, PencilIcon, PlusIcon, SearchIcon } from "../../components/supervisor/Icons";
import LocationFormDialog from "../../components/supervisor/LocationFormDialog";
import { EmptyState, ErrorState, LoadingState, Notice } from "../../components/supervisor/StateViews";
import { useQuery } from "../../hooks/useQuery";
import { safeExternalUrl } from "../../lib/validation";
import { useEventsApi } from "../../services/events/useEventsApi";

export default function Locations() {
  const api = useEventsApi();
  const locationsQuery = useQuery("locations", () => api.getLocations());
  const [search, setSearch] = useState("");
  const [dialog, setDialog] = useState(null);
  const [notice, setNotice] = useState("");

  const locations = locationsQuery.latestData;
  const term = search.trim().toLowerCase();
  const visible = (locations ?? []).filter(
    (location) =>
      !term ||
      location.building.toLowerCase().includes(term) ||
      location.room_or_area.toLowerCase().includes(term),
  );

  async function handleSave(values) {
    const saved =
      dialog.mode === "edit"
        ? await api.updateLocation(dialog.location.location_id, values)
        : await api.createLocation(values);
    setDialog(null);
    setNotice(
      `${saved.building} · ${saved.room_or_area} ${dialog.mode === "edit" ? "updated" : "added"}.`,
    );
    locationsQuery.reload();
  }

  let content;
  if (locationsQuery.error) {
    content = (
      <ErrorState
        title="We couldn't load locations"
        error={locationsQuery.error}
        onRetry={locationsQuery.reload}
      />
    );
  } else if (!locations) {
    content = <LoadingState label="Loading locations…" />;
  } else if (visible.length === 0) {
    content = term ? (
      <EmptyState title="No locations match your search">Try a different building or room.</EmptyState>
    ) : (
      <EmptyState
        title="No locations yet"
        action={
          <button type="button" className="btn btn-primary" onClick={() => setDialog({ mode: "create" })}>
            Add a location
          </button>
        }
      >
        Locations you add can be picked for any shift.
      </EmptyState>
    );
  } else {
    content = (
      <div className="table-wrap">
        <table>
          <caption className="visually-hidden">Locations</caption>
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">Building</th>
              <th scope="col">Room or area</th>
              <th scope="col">Directions</th>
              <th scope="col">Map</th>
              <th scope="col" className="num">
                Shifts
              </th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((location) => {
              const mapUrl = safeExternalUrl(location.map_url);
              const name = `${location.building} · ${location.room_or_area}`;
              return (
                <tr key={location.location_id}>
                  <td className="muted">#{location.location_id}</td>
                  <td>{location.building}</td>
                  <td>{location.room_or_area}</td>
                  <td className="cell-wrap">{location.directions || <span className="muted">—</span>}</td>
                  <td>
                    {mapUrl ? (
                      <a className="text-link" href={mapUrl} target="_blank" rel="noopener noreferrer">
                        Open map
                        <ExternalLinkIcon size={14} />
                        <span className="visually-hidden"> for {name} (opens in a new tab)</span>
                      </a>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td className="num">{location.shift_count}</td>
                  <td className="cell-actions">
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Edit ${name}`}
                      title="Edit location"
                      onClick={() => setDialog({ mode: "edit", location })}
                    >
                      <PencilIcon size={18} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Locations</h1>
          <p className="page-subtitle">
            Shared places that shifts can use. Editing a location updates it everywhere it&apos;s
            used; to move a single shift, pick a different location on that shift.
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setDialog({ mode: "create" })}>
          <PlusIcon size={18} />
          Add location
        </button>
      </div>

      <Notice onDismiss={() => setNotice("")}>{notice}</Notice>

      <div className="toolbar">
        <div className="search-field">
          <label htmlFor="location-search" className="visually-hidden">
            Search locations
          </label>
          <SearchIcon size={18} />
          <input
            id="location-search"
            type="search"
            className="input"
            placeholder="Search by building or room…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        {locations && (
          <p className="hint" role="status">
            {visible.length} of {locations.length} location{locations.length === 1 ? "" : "s"}
          </p>
        )}
      </div>

      {content}

      {dialog && (
        <LocationFormDialog
          location={dialog.mode === "edit" ? dialog.location : null}
          existingLocations={locations ?? []}
          onSave={handleSave}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}
