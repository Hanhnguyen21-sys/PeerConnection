export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? 'http://localhost:8000' : '')
).replace(/\/+$/, '')

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function profileErrorMessage(status) {
  if (status === 401) {
    return 'Your session has expired. Please sign out and sign in again.'
  }
  if (status === 404) {
    return "We couldn't find your profile yet. If you just signed up, wait a moment and try again."
  }
  if (status === 503) {
    return 'The sign-in service is temporarily unavailable. Please try again shortly.'
  }
  return 'Something went wrong while loading your profile. Please try again.'
}

export async function fetchMe(accessToken, { signal } = {}) {
  let response
  try {
    response = await fetch(`${API_BASE_URL}/api/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError(
      "We couldn't reach the Peer Connections server. Check your connection and try again.",
      0,
    )
  }

  if (!response.ok) {
    throw new ApiError(profileErrorMessage(response.status), response.status)
  }

  return response.json()
}
