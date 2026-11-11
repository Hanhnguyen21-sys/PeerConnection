// Error type shared by every event-data service implementation.
export class ServiceError extends Error {
  constructor(message, { status = 500, fieldErrors = null, code = null } = {}) {
    super(message);
    this.name = "ServiceError";
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.code = code;
  }
}

export function isNotFoundError(error) {
  return error?.status === 404;
}
