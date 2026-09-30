import { notifications } from "@mantine/notifications";

export function notifySuccess(message: string) {
  notifications.show({ color: "green", message, autoClose: 3000 });
}

export function notifyError(error: unknown, fallback = "Aktion fehlgeschlagen") {
  const message = error instanceof Error && error.message ? error.message : fallback;
  notifications.show({ color: "red", title: fallback, message, autoClose: 6000 });
}
