export { api, call } from "./client";
export type { Schemas } from "./client";
import { isProcessing } from "../lib/format";

export function isProcessingAny(
  docs: { ocr_status: string; classification_status: string; extraction_status: string }[],
): boolean {
  return docs.some(isProcessing);
}
