import { fetchBackupFile, fetchDocumentFile, type DocumentDetail } from "../api/client";

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Originaldatei herunterladen (mit Anmeldung). */
export async function downloadDocument(doc: DocumentDetail) {
  saveBlob(await fetchDocumentFile(doc.id), doc.files[0]?.filename ?? doc.title);
}

/** Datenbanksicherung herunterladen (mit Anmeldung, nur Admins). */
export async function downloadBackup(name: string) {
  saveBlob(await fetchBackupFile(name), name);
}
