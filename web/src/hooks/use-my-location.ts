import { useEffect } from 'react'
import { useGeolocationStore } from '@/store/geolocation-store'

/**
 * Requests browser geolocation permission and watches the laptop's own GPS
 * position, independent of any drone telemetry. Meant to be mounted exactly
 * once (see `MyLocationMarker`) — reads elsewhere should go through
 * `useGeolocationStore` instead of calling this hook again, which would
 * start a second `watchPosition` subscription.
 */
export function useMyLocation(): void {
  const setPosition = useGeolocationStore((s) => s.setPosition)
  const setStatus = useGeolocationStore((s) => s.setStatus)
  const setError = useGeolocationStore((s) => s.setError)

  useEffect(() => {
    // The Geolocation API is only available in a "secure context" — HTTPS,
    // or http://localhost. Opening this app at a plain-HTTP LAN address
    // (e.g. http://<pi-ip>:8000, which is how it's normally reached from a
    // laptop on the same network) makes every browser refuse geolocation
    // outright, with no prompt at all — surface that distinctly so it
    // doesn't just look like a silent failure.
    if (!window.isSecureContext) {
      setStatus('insecure-context')
      return
    }
    if (!('geolocation' in navigator)) {
      setStatus('unsupported')
      return
    }

    setStatus('requesting')
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        setPosition({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        })
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setStatus('denied')
        } else {
          setError(err.message || 'Unable to determine your location.')
        }
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 },
    )

    return () => navigator.geolocation.clearWatch(watchId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
