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
