// Maps Supabase Auth errors to messages that are safe and helpful to show users.
export function getAuthErrorMessage(error) {
  const code = error?.code
  const message = error?.message?.toLowerCase() ?? ''

  if (code === 'invalid_credentials' || message.includes('invalid login credentials')) {
    return 'Incorrect email or password.'
  }
  if (code === 'email_not_confirmed' || message.includes('email not confirmed')) {
    return 'Please confirm your email address first. Check your inbox for the confirmation link.'
  }
  if (code === 'user_already_exists' || message.includes('already registered')) {
    return 'An account with this email already exists. Try signing in instead.'
  }
  if (code === 'weak_password') {
    return error.message || 'Please choose a stronger password.'
  }
  if (code === 'email_address_invalid') {
    return 'That email address is not valid. Please check it and try again.'
  }
  if (code === 'signup_disabled') {
    return 'New sign-ups are currently turned off. Please contact your supervisor.'
  }
  if (
    code === 'over_request_rate_limit' ||
    code === 'over_email_send_rate_limit' ||
    error?.status === 429
  ) {
    return 'Too many attempts. Please wait a moment and try again.'
  }
  if (error?.name === 'AuthRetryableFetchError' || message.includes('failed to fetch')) {
    return "We couldn't reach the sign-in service. Check your connection and try again."
  }
  return 'Something went wrong. Please try again.'
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function validateEmail(email) {
  if (!email.trim()) return 'Enter your email address.'
  if (!EMAIL_PATTERN.test(email.trim())) return 'Enter a valid email address, like name@example.com.'
  return ''
}
