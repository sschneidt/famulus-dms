/** Zahlungsfristen erkennen - dieselben Stichworte wie im Backend (core/payments.py), dazu
 * englische und russische fuer selbst eingetragene Termine. */
export function isPaymentNote(note?: string | null): boolean {
  return /zahl|überweis|ueberweis|fällig|faellig|begleich|payment|оплат|плат[её]ж/i.test(note ?? "");
}
