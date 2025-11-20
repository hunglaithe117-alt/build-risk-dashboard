import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Format duration from minutes to human-readable format
 * @param minutes - Duration in minutes (can be decimal)
 * @returns Formatted string like "2m 30s" or "45s"
 */
export function formatDuration(minutes?: number): string {
  if (!minutes) return "—";

  const totalSeconds = Math.round(minutes * 60);
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;

  if (mins === 0) {
    return `${secs}s`;
  }
  return `${mins}m ${secs}s`;
}

/**
 * Format duration from seconds to human-readable format
 * @param seconds - Duration in seconds
 * @returns Formatted string like "2m 30s" or "45s"
 */
export function formatDurationFromSeconds(seconds?: number): string {
  if (!seconds) return "—";

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);

  if (minutes === 0) {
    return `${remainingSeconds}s`;
  }
  return `${minutes}m ${remainingSeconds}s`;
}

/**
 * Format ISO timestamp to localized date and time
 * @param value - ISO date string
 * @returns Formatted date string or "—" if invalid
 */
export function formatTimestamp(value?: string): string {
  if (!value) return "—";

  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch (err) {
    return value;
  }
}
