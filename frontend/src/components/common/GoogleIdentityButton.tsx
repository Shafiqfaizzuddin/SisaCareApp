import { useEffect, useRef, useState } from 'react'
import { googleClientId, loadGoogleIdentity } from '../../features/authentication/google'

interface GoogleIdentityButtonProps {
  onCredential: (credential: string) => Promise<void>
  onError: (message: string) => void
  text?: string
  disabled?: boolean
}

function GoogleMark() {
  return <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#4285F4" d="M21.35 12.22c0-.7-.06-1.36-.18-2H12v3.77h5.24a4.47 4.47 0 0 1-1.95 2.94v2.44h3.16c1.85-1.7 2.9-4.2 2.9-7.15Z" />
    <path fill="#34A853" d="M12 21.75c2.65 0 4.88-.88 6.5-2.38l-3.16-2.44c-.88.59-2 .94-3.34.94-2.56 0-4.72-1.73-5.49-4.05H3.25v2.52A9.82 9.82 0 0 0 12 21.75Z" />
    <path fill="#FBBC05" d="M6.51 13.84a5.9 5.9 0 0 1 0-3.68V7.64H3.25a9.81 9.81 0 0 0 0 8.72l3.26-2.52Z" />
    <path fill="#EA4335" d="M12 6.21c1.44 0 2.73.5 3.74 1.47l2.81-2.82A9.39 9.39 0 0 0 12 2.25a9.82 9.82 0 0 0-8.75 5.39l3.26 2.52C7.28 7.94 9.44 6.21 12 6.21Z" />
  </svg>
}

export function GoogleIdentityButton({ onCredential, onError, text = 'continue_with', disabled = false }: GoogleIdentityButtonProps) {
  const container = useRef<HTMLDivElement>(null)
  const activeRequest = useRef(false)
  const disabledRef = useRef(disabled)
  disabledRef.current = disabled
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!googleClientId) return
    let active = true
    let resizeObserver: ResizeObserver | undefined
    void loadGoogleIdentity().then(() => {
      if (!active || !container.current || !window.google) return
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: ({ credential }) => {
          if (activeRequest.current || disabledRef.current) return
          activeRequest.current = true
          setLoading(true)
          void onCredential(credential).catch((error: unknown) => {
            onError(error instanceof Error ? error.message : 'Google sign-in failed.')
          }).finally(() => { activeRequest.current = false; setLoading(false) })
        },
      })
      const render = () => {
        if (!container.current || !window.google) return
        const width = Math.min(400, Math.max(220, Math.floor(container.current.getBoundingClientRect().width)))
        container.current.replaceChildren()
        window.google.accounts.id.renderButton(container.current, {
          theme: 'outline', size: 'large', text, width,
        })
      }
      render()
      if (typeof ResizeObserver !== 'undefined') {
        resizeObserver = new ResizeObserver(render)
        resizeObserver.observe(container.current)
      }
    }).catch(() => onError('Google sign-in is temporarily unavailable.'))
    return () => { active = false; resizeObserver?.disconnect() }
  }, [onCredential, onError, text])

  if (!googleClientId) {
    return <button className="google-sign-in google-sign-in--fallback" type="button" disabled={disabled}
      onClick={() => onError('Google sign-in is temporarily unavailable.')}>
      <GoogleMark /> Continue with Google
    </button>
  }
  return <div className={`google-sign-in${disabled || loading ? ' google-sign-in--disabled' : ''}`}
    aria-busy={loading}>
    <div ref={container} className="google-sign-in__widget" inert={disabled || loading} />
  </div>
}
