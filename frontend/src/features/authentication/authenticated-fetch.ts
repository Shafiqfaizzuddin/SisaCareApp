export class AuthenticatedRequestError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AuthenticatedRequestError'
  }
}

async function fetchWithAuthentication(
  input: RequestInfo | URL,
  init: RequestInit = {},
  required: boolean,
): Promise<Response> {
  const response = await fetch(input, { ...init, credentials: 'same-origin' })
  if (required && response.status === 401) throw new AuthenticatedRequestError('Your session has expired. Please sign in again.')
  return response
}

export function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  return fetchWithAuthentication(input, init, true)
}

export function optionallyAuthenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  return fetchWithAuthentication(input, init, false)
}
