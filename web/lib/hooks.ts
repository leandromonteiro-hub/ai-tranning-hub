"use client";
import useSWR from 'swr'
import { jsonFetcher } from '@/lib/api'
import type { AdminFeedback, Athlete, AthleteIntelligence, AthleteProfile, CalendarResponse, CompletedWorkout, GarminStatus, Invite, LoadMetric, Race, Recommendation, UsageMetrics, WorkoutStreams } from '@/lib/types'

export function useCalendar(start: string, end: string) {
  return useSWR<CalendarResponse>(`calendar?start=${start}&end=${end}`, jsonFetcher as (p: string) => Promise<CalendarResponse>)
}

export function useWorkouts(start: string, end: string) {
  return useSWR<CompletedWorkout[]>(`workouts?start=${start}&end=${end}`, jsonFetcher as (p: string) => Promise<CompletedWorkout[]>)
}

export function useWorkoutStreams(id: string | null) {
  return useSWR<WorkoutStreams>(id ? `workouts/${id}/streams` : null, jsonFetcher as (p: string) => Promise<WorkoutStreams>)
}

export function useIntelligence() {
  return useSWR<AthleteIntelligence>('athletes/me/intelligence', jsonFetcher as (p: string) => Promise<AthleteIntelligence>)
}

export function useLoadSeries(start: string, end: string) {
  return useSWR<LoadMetric[]>(`metrics/load?start=${start}&end=${end}`, jsonFetcher as (p: string) => Promise<LoadMetric[]>)
}

export function useRecommendations() {
  return useSWR<Recommendation[]>('recommendations', jsonFetcher as (p: string) => Promise<Recommendation[]>)
}

export function useRaces() {
  return useSWR<Race[]>('races', jsonFetcher as (p: string) => Promise<Race[]>)
}

export function useProfile() {
  return useSWR<AthleteProfile | null>('athletes/me/profile', jsonFetcher as (p: string) => Promise<AthleteProfile | null>)
}

export function useAdminUsage() {
  return useSWR<UsageMetrics>('admin/usage', jsonFetcher as (p: string) => Promise<UsageMetrics>)
}

export function useAdminAthletes() {
  return useSWR<Athlete[]>('admin/athletes', jsonFetcher as (p: string) => Promise<Athlete[]>)
}

export function useAdminFeedback() {
  return useSWR<AdminFeedback[]>('admin/feedback', jsonFetcher as (p: string) => Promise<AdminFeedback[]>)
}

export function useGarminStatus() {
  // 503 = feature desligada — não adianta re-tentar.
  return useSWR<GarminStatus>('garmin/status', jsonFetcher as (p: string) => Promise<GarminStatus>, {
    shouldRetryOnError: false,
  })
}

export function useInvites() {
  return useSWR<Invite[]>('admin/invites', jsonFetcher as (p: string) => Promise<Invite[]>)
}
