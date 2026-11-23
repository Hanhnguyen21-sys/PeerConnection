import { useState } from "react";
import { ConfirmDialog } from "../../components/Modal";
import { SearchIcon } from "../../components/supervisor/Icons";
import { EmptyState, ErrorState, LoadingState, Notice } from "../../components/supervisor/StateViews";
import { useQuery } from "../../hooks/useQuery";
import { useEventsApi } from "../../services/events/useEventsApi";

const ROLE_NAMES = { supervisor: "Supervisor", peer_educator: "Peer educator" };

// Supervisors decide who else is a supervisor. Everyone signs up as a peer
// educator; nobody can change their own role (the backend enforces both).
export default function People() {
  const api = useEventsApi();
  const usersQuery = useQuery("people", () => api.getUsers());
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(null); // { user, role }
  const [dialogError, setDialogError] = useState("");
  const [isWorking, setIsWorking] = useState(false);

  const users = usersQuery.latestData;
  const term = search.trim().toLowerCase();
  const visible = (users ?? []).filter(
    (user) => !term || user.name.toLowerCase().includes(term) || user.email.toLowerCase().includes(term),
  );
  const supervisorCount = (users ?? []).filter((user) => user.role === "supervisor").length;

  function openChange(user) {
    setDialogError("");
    setPending({ user, role: user.role === "supervisor" ? "peer_educator" : "supervisor" });
  }

  async function handleConfirm() {
    setIsWorking(true);
    setDialogError("");
    try {
      const updated = await api.setUserRole(pending.user.user_id, pending.role);
      setPending(null);
      setNotice(`${updated.name || updated.email} is now a ${ROLE_NAMES[updated.role].toLowerCase()}.`);
      usersQuery.reload();
    } catch (error) {
      setDialogError(error.message || "We couldn't change this role. Please try again.");
    } finally {
      setIsWorking(false);
    }
  }

  let content;
  if (usersQuery.error) {
    content = <ErrorState title="We couldn't load people" error={usersQuery.error} onRetry={usersQuery.reload} />;
  } else if (!users) {
    content = <LoadingState label="Loading people…" />;
  } else if (visible.length === 0) {
    content = term ? (
      <EmptyState title="No one matches your search">Try a different name or email.</EmptyState>
    ) : (
      <EmptyState title="No accounts yet">People appear here after they sign up.</EmptyState>
    );
  } else {
    content = (
      <div className="table-wrap">
        <table>
          <caption className="visually-hidden">People with an account</caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Email</th>
              <th scope="col">Role</th>
              <th scope="col" className="num">
                Upcoming sign-ups
              </th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((user) => (
              <tr key={user.user_id}>
                <td>
                  {user.name || <span className="muted">No name</span>}
                  {user.is_you && <span className="muted"> (you)</span>}
                </td>
                <td>
                  <a className="text-link" href={`mailto:${user.email}`}>
                    {user.email}
                  </a>
                </td>
                <td>
                  <span className={`badge ${user.role === "supervisor" ? "badge-role-supervisor" : "badge-role-educator"}`}>
                    {ROLE_NAMES[user.role] ?? user.role}
                  </span>
                </td>
                <td className="num">{user.upcoming_registrations}</td>
                <td className="cell-actions">
                  {user.is_you ? (
                    <span className="hint">Another supervisor can change your role</span>
                  ) : (
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => openChange(user)}>
                      {user.role === "supervisor" ? "Make peer educator" : "Make supervisor"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  const promoting = pending?.role === "supervisor";
  const pendingName = pending ? pending.user.name || pending.user.email : "";

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">People</h1>
          <p className="page-subtitle">
            Everyone signs up as a peer educator. Make someone a supervisor here so they can manage
            events, take attendance and see reports. You can&apos;t change your own role.
          </p>
        </div>
      </div>

      <Notice onDismiss={() => setNotice("")}>{notice}</Notice>

      <div className="toolbar">
        <div className="search-field">
          <label htmlFor="people-search" className="visually-hidden">
            Search people
          </label>
          <SearchIcon size={18} />
          <input
            id="people-search"
            type="search"
            className="input"
            placeholder="Search by name or email…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        {users && (
          <p className="hint" role="status">
            {visible.length} of {users.length} {users.length === 1 ? "person" : "people"} · {supervisorCount}{" "}
            supervisor{supervisorCount === 1 ? "" : "s"}
          </p>
        )}
      </div>

      {content}

      {pending && (
        <ConfirmDialog
          title={promoting ? `Make ${pendingName} a supervisor?` : `Make ${pendingName} a peer educator?`}
          confirmLabel={promoting ? "Make supervisor" : "Make peer educator"}
          cancelLabel="Keep current role"
          tone={promoting ? "primary" : "danger"}
          isBusy={isWorking}
          error={dialogError}
          onConfirm={handleConfirm}
          onCancel={() => setPending(null)}
        >
          {promoting ? (
            <p>
              They&apos;ll be able to create and cancel events, take attendance, see reports and
              change other people&apos;s roles. They&apos;ll no longer sign up for shifts.
            </p>
          ) : (
            <p>
              They&apos;ll lose access to the supervisor dashboard and can sign up for shifts again.
              Events they organized stay as they are.
            </p>
          )}
        </ConfirmDialog>
      )}
    </>
  );
}
