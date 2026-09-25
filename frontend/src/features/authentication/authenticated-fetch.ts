import { supabaseClient } from '../../lib/supabase'


export class AuthenticatedRequestError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AuthenticatedRequestError'
  }
}

async function authorizationHeader(required: boolean): Promise<string | null> {
  if (!supabaseClient) {
    if (required) {
      throw new AuthenticatedRequestError(
        'Authentication is not configured. Please sign in again after configuration is restored.',
      )
    }
    return null
  }

  const { data, error } = await supabaseClient.auth.getSession()
  const token = data.session?.access_token
  if (error || !token) {
    if (required) {
      throw new AuthenticatedRequestError(
        'Your session has expired. Please sign in again.',
      )
    }
    return null
  }
  return `Bearer ${token}`
}

async function fetchWithAuthentication(
  input: RequestInfo | URL,
  init: RequestInit = {},
  required: boolean,
): Promise<Response> {
  const authorization = await authorizationHeader(required)
  const headers = new Headers(init.headers)
  if (authorization) {
    headers.set('Authorization', authorization)
  }
  return fetch(input, { ...init, headers })
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
