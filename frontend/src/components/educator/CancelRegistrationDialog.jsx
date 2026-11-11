import { formatDate, formatTimeRange } from "../../lib/campusTime";
import { locationName } from "../../lib/locations";
import { ConfirmDialog } from "../Modal";

// Confirms cancelling the signed-in user's own registration.
export default function CancelRegistrationDialog({
  eventTitle,
  shift,
  location,
  isBusy,
  error,
  onConfirm,
  onCancel,
}) {
  return (
    <ConfirmDialog
      title="Cancel your registration?"
      confirmLabel="Cancel registration"
      cancelLabel="Keep registration"
      isBusy={isBusy}
      error={error}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <p>
        <strong>{eventTitle}</strong>
        <br />
        {formatDate(shift.shift_date)}, {formatTimeRange(shift.start_time, shift.end_time)}
        <br />
        {locationName(location)}
      </p>
      <p>
        Your spot will be released for other peer educators. You can register again later if a spot
        is still open.
      </p>
    </ConfirmDialog>
  );
}
