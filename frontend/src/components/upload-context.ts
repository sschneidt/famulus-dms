import { createContext, useContext } from "react";

export type UploadMode = "files" | "camera";
export const UploadContext = createContext<(mode?: UploadMode) => void>(() => undefined);

/** Oeffnet den Upload-Dialog bzw. direkt die Kamera (von ueberall in der App). */
export function useOpenUpload() {
  return useContext(UploadContext);
}
