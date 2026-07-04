// MAVLink command IDs relevant to rendering a mission on the map.
// Mirrors the subset used by server/services/grid_planner.py and the parsers.
export const MAV_CMD = {
  NAV_WAYPOINT: 16,
  NAV_RTL: 20,
  NAV_LAND: 21,
  NAV_TAKEOFF: 22,
  DO_CHANGE_SPEED: 178,
} as const

export const FLIGHT_MODE_LABELS: Record<string, string> = {
  STABILIZE: 'Stabilize',
  ACRO: 'Acro',
  ALT_HOLD: 'Altitude Hold',
  AUTO: 'Auto',
  GUIDED: 'Guided',
  LOITER: 'Loiter',
  RTL: 'Return to Launch',
  CIRCLE: 'Circle',
  LAND: 'Land',
  POSHOLD: 'Position Hold',
  BRAKE: 'Brake',
  SMART_RTL: 'Smart RTL',
  UNKNOWN: 'Unknown',
}
