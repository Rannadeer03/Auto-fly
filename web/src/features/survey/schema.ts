import { z } from 'zod'

// Mirrors server/services/grid_planner.py:GridParams.validate() ranges, so
// the form rejects invalid input before it ever reaches the backend.
export const flightParamsSchema = z.object({
  altitudeM: z.number().min(2).max(500),
  speedMs: z.number().min(0.5).max(25),
  frontOverlapPct: z.number().min(0).max(95),
  sideOverlapPct: z.number().min(0).max(95),
  angleDeg: z.number().min(0).max(359),
  surveyDirection: z.enum(['auto', 'manual']),
  holdTimeS: z.number().min(0).max(30),
  captureMode: z.enum(['hover', 'continuous']),
  cameraAngleDeg: z.number().min(-90).max(0),
  imageFormat: z.enum(['jpeg', 'png']),
  missionName: z.string().max(120),
  missionDescription: z.string().max(500),
})

export type FlightParamsFormValues = z.infer<typeof flightParamsSchema>
