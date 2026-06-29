"use client";
import useSWR from 'swr'
import { jsonFetcher } from '@/lib/api'
import type { CalendarResponse, WorkoutStreams } from '@/lib/types'

export function useCalendar(start: string, end: string) {
  return useSWR<CalendarResponse>(`calendar?start=${start}&end=${end}`, jsonFetcher as (p: string) => Promise<CalendarResponse>)
}

export function useWorkoutStreams(id: string | null) {
  return useSWR<WorkoutStreams>(id ? `workouts/${id}/streams` : null, jsonFetcher as (p: string) => Promise<WorkoutStreams>)
}
