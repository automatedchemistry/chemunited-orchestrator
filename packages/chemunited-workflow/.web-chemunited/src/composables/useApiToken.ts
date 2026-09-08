import { ref } from 'vue'
import { useNotification } from './useNotification'

const STORAGE_KEY = 'chemunited-api-token'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

const token = ref<string>(localStorage.getItem(STORAGE_KEY) ?? '')

export function useApiToken() {
  function setToken(value: string) {
    token.value = value.trim()
    if (token.value) localStorage.setItem(STORAGE_KEY, token.value)
    else localStorage.removeItem(STORAGE_KEY)
  }
  return { token, setToken }
}

function isSameOrigin(input: RequestInfo | URL): boolean {
  try {
    const url = input instanceof Request ? input.url : input.toString()
    return new URL(url, window.location.href).origin === window.location.origin
  } catch {
    return false
  }
}

let installed = false

/**
 * Attaches the saved API token to same-origin, state-changing fetch()
 * calls (POST/PUT/DELETE/...) so a remote dashboard user can still act on
 * the backend once they've set a token — see AccessControlMiddleware on
 * the server, which only requires the token for non-loopback callers.
 */
export function installApiTokenFetchInterceptor() {
  if (installed) return
  installed = true
  const originalFetch = window.fetch.bind(window)
  const { notify } = useNotification()

  window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const method = (
      init.method ?? (input instanceof Request ? input.method : 'GET')
    ).toUpperCase()

    let request = init
    if (!SAFE_METHODS.has(method) && token.value && isSameOrigin(input)) {
      const headers = new Headers(
        init.headers ?? (input instanceof Request ? input.headers : undefined),
      )
      if (!headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token.value}`)
      }
      request = { ...init, headers }
    }

    const response = await originalFetch(input, request)
    if (response.status === 401 && !SAFE_METHODS.has(method)) {
      notify(
        'Remote action rejected — set a valid API token (sidebar, bottom-left) to control this instance from another machine.',
        'error',
      )
    }
    return response
  }
}
