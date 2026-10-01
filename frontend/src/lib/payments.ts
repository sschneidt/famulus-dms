/** Zahlungsfristen erkennen - dieselben Stichworte wie im Backend (core/payments.py). */
export function isPaymentNote(note?: string | null): boolean {
  return /zahl|überweis|ueberweis|fällig|faellig|begleich/i.test(note ?? "");
}
