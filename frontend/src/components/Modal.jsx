import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { XIcon } from "./supervisor/Icons";

// Accessible modal built on the native <dialog>: focus stays inside, Escape
// closes, and focus returns to the control that opened it. Rendered in a
// portal so a form inside it never nests in a page form.
export function Modal({ title, onClose, initialFocusRef, children, className = "" }) {
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const titleId = useId();

  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    const previouslyFocused = document.activeElement;
    dialog.showModal();
    initialFocusRef?.current?.focus();
    return () => {
      if (dialog.open) dialog.close();
      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, [initialFocusRef]);

  return createPortal(
    <dialog
      ref={dialogRef}
      className={`modal ${className}`}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onCloseRef.current();
      }}
    >
      <div className="modal-header">
        <h2 className="modal-title" id={titleId}>
          {title}
        </h2>
        <button type="button" className="icon-button" onClick={() => onCloseRef.current()} aria-label="Close dialog">
          <XIcon />
        </button>
      </div>
      {children}
    </dialog>,
    document.body,
  );
}

export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  cancelLabel = "Go back",
  tone = "danger",
  isBusy = false,
  error = "",
  onConfirm,
  onCancel,
}) {
  const cancelRef = useRef(null);
  const close = () => {
    if (!isBusy) onCancel();
  };

  return (
    <Modal title={title} onClose={close} initialFocusRef={cancelRef}>
      <div className="modal-body">
        <div className="modal-text">{children}</div>
        <div className="form-alert" role="alert">
          {error}
        </div>
        <div className="modal-actions">
          <button ref={cancelRef} type="button" className="btn btn-secondary" onClick={close} disabled={isBusy}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={tone === "danger" ? "btn btn-danger-solid" : "btn btn-primary"}
            onClick={onConfirm}
            disabled={isBusy}
          >
            {isBusy && <span className="spinner" aria-hidden="true" />}
            {isBusy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
