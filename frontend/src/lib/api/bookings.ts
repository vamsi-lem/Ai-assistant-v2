/**
 * Bookings (appointments) and counsellor availability.
 *
 * Backend: backend/app/routers/bookings.py
 */

import { request, qs } from "@/lib/api/client";
import type { Availability, Booking, BookingInput, BookingStatus } from "@/lib/types";

export function listBookings(daysBack = 1, daysAhead = 30): Promise<Booking[]> {
  return request<Booking[]>(`/bookings${qs({ days_back: daysBack, days_ahead: daysAhead })}`);
}

/** Free and taken slots for one counsellor on one day (YYYY-MM-DD). */
export function getAvailability(counsellorId: string, date: string): Promise<Availability> {
  return request<Availability>(`/bookings/availability${qs({ counsellor_id: counsellorId, date })}`);
}

/**
 * Book from the dashboard. Goes through the same service Maya uses, so the
 * meeting link and the WhatsApp message happen exactly as on a call.
 */
export function createBooking(input: BookingInput): Promise<Booking> {
  return request<Booking>("/bookings/dashboard", { method: "POST", body: input });
}

export function resendWhatsApp(id: string): Promise<Booking> {
  return request<Booking>(`/bookings/${id}/resend`, { method: "POST" });
}

export function setBookingStatus(id: string, status: BookingStatus): Promise<Booking> {
  return request<Booking>(`/bookings/${id}/status`, { method: "POST", body: { status } });
}
