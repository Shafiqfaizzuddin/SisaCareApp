import { useEffect, useState } from 'react'
import { authenticatedFetch } from '../../features/authentication/authenticated-fetch'

export function PrivateImage({ src, alt }: { src: string; alt: string }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl = ''
    void authenticatedFetch(src, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('Photo unavailable')
      const blob = await response.blob()
      if (controller.signal.aborted) return
      objectUrl = URL.createObjectURL(blob)
      setUrl(objectUrl)
    }).catch(() => { if (!controller.signal.aborted) setError(true) })
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [src])
  if (error) return <span role="status">Photo unavailable.</span>
  if (!url) return <span role="status">Loading photo...</span>
  return <img src={url} alt={alt} />
}
