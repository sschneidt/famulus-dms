import { fetchDocumentFile, type DocumentDetail } from "../api/client";

/** Originaldatei herunterladen (mit Anmeldung). */
export async function downloadDocument(doc: DocumentDetail) {
  const blob = await fetchDocumentFile(doc.id);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = doc.files[0]?.filename ?? doc.title;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
