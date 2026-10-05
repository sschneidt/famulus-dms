import { notifications } from "@mantine/notifications";
import i18n from "../i18n";

export function notifySuccess(message: string) {
  notifications.show({ color: "green", message, autoClose: 3000 });
}

export function notifyError(error: unknown, fallbackText?: string) {
  const fallback = fallbackText ?? i18n.t("Aktion fehlgeschlagen");
  const message = error instanceof Error && error.message ? error.message : fallback;
  notifications.show({ color: "red", title: fallback, message, autoClose: 6000 });
}
