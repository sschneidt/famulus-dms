import type { Category, DocumentItem, Me, Wiedervorlage } from "../api/client";

export const me: Me = {
  id: "u1",
  tenant_id: "t1",
  email: "anna@example.com",
  display_name: "Anna Muster",
  role: "admin",
  locale: "de",
  household_name: "Familie Muster",
  two_factor_enabled: false,
};

export const categories: Category[] = [
  {
    id: "c-rech",
    name: "Rechnungen",
    description: "",
    is_restricted: false,
    is_system_default: true,
    property_mode: "none",
  },
  {
    id: "c-vers",
    name: "Versicherungen",
    description: "",
    is_restricted: false,
    is_system_default: true,
    property_mode: "none",
  },
];

export function doc(overrides: Partial<DocumentItem> = {}): DocumentItem {
  return {
    id: "d1",
    title: "Stromrechnung September",
    title_locked: false,
    subject: "Stromrechnung September",
    property_id: null,
    category_id: "c-rech",
    owner_user_id: "u1",
    source: "upload",
    ocr_status: "done",
    classification_status: "auto_assigned",
    classification_confidence: 0.91,
    classification_stage: "embedding",
    extraction_status: "done",
    document_date: "2026-09-12",
    issuer: "Stadtwerke Musterstadt",
    amount: 84.5,
    original_present: "unbekannt",
    original_location: null,
    is_invoice: null,
    is_invoice_locked: false,
    payment_status: null,
    paid_on: null,
    paid_assumed: false,
    deleted_at: null,
    created_at: "2026-09-28T10:00:00Z",
    updated_at: "2026-09-28T10:01:00Z",
    files: [
      {
        id: "f1",
        page_number: 1,
        mime_type: "application/pdf",
        filename: "strom.pdf",
        path: "Familie Muster/Rechnungen/2026/strom.pdf",
      },
    ],
    ...overrides,
  };
}

export function wv(overrides: Partial<Wiedervorlage> = {}): Wiedervorlage {
  return {
    id: "w1",
    document_id: "d1",
    due_date: "2026-10-15",
    note: "Zahlungsfrist Stromrechnung",
    type: "custom",
    source: "ai_suggested",
    status: "vorgeschlagen",
    confidence: 0.8,
    source_snippet: "zahlbar bis 15.10.2026",
    recurrence: "none",
    recurrence_interval_months: null,
    assigned_user_id: null,
    reminder_lead_days: 7,
    completed_at: null,
    created_at: "2026-09-28T10:01:00Z",
    updated_at: "2026-09-28T10:01:00Z",
    document_title: "Stromrechnung September",
    ...overrides,
  };
}

export const page = <T,>(items: T[]) => ({ items, page: 1, page_size: 25, total: items.length });
