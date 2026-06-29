"use client";
import useSWR from 'swr'
import { jsonFetcher } from '@/lib/api'
import type { AthleteIntelligence, CalendarResponse, CompletedWorkout, LoadMetric, Recommendation, WorkoutStreams } from '@/lib/types'

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
