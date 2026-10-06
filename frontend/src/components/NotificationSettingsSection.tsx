import { ActionIcon, Alert, Badge, Button, Group, Loader, Select, Stack, Switch, Text, Tooltip } from "@mantine/core";
import { IconBellRinging, IconDeviceMobile, IconMail, IconTrash } from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router";
import {
  useNotificationSettings,
  useRemovePushDevice,
  useSubscribePush,
  useTestNotification,
  useUpdateNotificationSettings,
} from "../api/queries";
import { formatDateTime, tk } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";
import { currentEndpoint, pushSupport, subscribePush, unsubscribePush } from "../lib/push";

const HOURS = Array.from({ length: 24 }, (_, h) => ({
  value: String(h),
  label: String(h).padStart(2, "0"),
}));

/**
 * Konto & Sicherheit > Benachrichtigungen: Uhrzeit der taeglichen Zusammenfassung, E-Mail an/aus,
 * Push auf diesem Geraet, Liste der Geraete mit Push, Testnachrichten.
 */
export function NotificationSettingsSection() {
  const settings = useNotificationSettings();
  const { t } = useTranslation();
  const update = useUpdateNotificationSettings();
  const test = useTestNotification();
  const ref = useRef<HTMLDivElement>(null);
  const location = useLocation();

  useEffect(() => {
    if (location.hash === "#benachrichtigungen" && settings.data) ref.current?.scrollIntoView({ behavior: "smooth" });
  }, [location.hash, settings.data]);

  if (settings.isPending) return <Loader size="sm" />;
  if (settings.isError) return <Alert color="red">{settings.error.message}</Alert>;
  const s = settings.data;

  function save(body: Parameters<typeof update.mutate>[0]) {
    update.mutate(body, { onError: (e) => notifyError(e, t("Speichern fehlgeschlagen")) });
  }

  function sendTest(channel: "email" | "push") {
    test.mutate(channel, {
      onSuccess: (r) => (r.ok ? notifySuccess(r.message) : notifyError(new Error(r.message), t("Test fehlgeschlagen"))),
      onError: (e) => notifyError(e, t("Test fehlgeschlagen")),
    });
  }

  return (
    <Stack ref={ref} id="benachrichtigungen" gap="md">
      <Text size="sm" c="dimmed">
        {t(
          "Einmal täglich eine Zusammenfassung – nur wenn etwas ansteht: Termine im Vorlauf, eine Woche und einen Tag vorher, am Tag selbst und danach wöchentlich, bis sie erledigt sind. Dazu neue Fristvorschläge der KI und Dokumente zum Prüfen. In der App (Glocke oben) erscheint sie immer.",
        )}
      </Text>
      <Select
        label={t("Uhrzeit")}
        description={t("Zeitzone des Servers: {{tz}}", { tz: s.timezone })}
        data={HOURS.map((h) => ({ value: h.value, label: t(tk("{{hour}}:00 Uhr"), { hour: h.label }) }))}
        value={String(s.digest_hour)}
        onChange={(v) => v !== null && save({ digest_hour: Number(v) })}
        allowDeselect={false}
        maw={220}
      />

      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Switch
          label={
            <Group gap={6}>
              <IconMail size={16} /> {t("Per E-Mail an {{email}}", { email: s.email_address })}
            </Group>
          }
          description={
            s.email_available
              ? undefined
              : t("Der E-Mail-Versand ist noch nicht eingerichtet (Admin: Seite „Benutzer“ > „E-Mail-Versand“).")
          }
          checked={s.email && s.email_available}
          disabled={!s.email_available}
          onChange={(e) => save({ email: e.currentTarget.checked })}
        />
        {s.email && s.email_available && (
          <Button
            size="xs"
            variant="default"
            onClick={() => sendTest("email")}
            loading={test.isPending && test.variables === "email"}
          >
            {t("Test-E-Mail")}
          </Button>
        )}
      </Group>

      <PushSettings
        publicKey={s.push_public_key}
        devices={s.push_devices}
        enabled={s.push}
        onToggle={(push) => save({ push })}
        onTest={() => sendTest("push")}
        testing={test.isPending && test.variables === "push"}
      />
    </Stack>
  );
}

interface Device {
  id: string;
  name: string;
  endpoint: string;
  created_at: string;
  last_success_at?: string | null;
  last_error?: string | null;
}

function PushSettings({
  publicKey,
  devices,
  enabled,
  onToggle,
  onTest,
  testing,
}: {
  publicKey: string;
  devices: Device[];
  enabled: boolean;
  onToggle(on: boolean): void;
  onTest(): void;
  testing: boolean;
}) {
  const { t } = useTranslation();
  const support = pushSupport();
  const subscribe = useSubscribePush();
  const remove = useRemovePushDevice();
  const [endpoint, setEndpoint] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    currentEndpoint().then(setEndpoint, () => setEndpoint(null));
  }, [devices]);

  const thisDevice = devices.find((d) => d.endpoint === endpoint);

  async function turnOn() {
    setBusy(true);
    try {
      const sub = await subscribePush(publicKey);
      await subscribe.mutateAsync(sub);
      setEndpoint(sub.endpoint);
      notifySuccess(t("Push auf diesem Gerät eingeschaltet"));
    } catch (e) {
      notifyError(e, t("Push einschalten fehlgeschlagen"));
    } finally {
      setBusy(false);
    }
  }

  async function turnOff(device: Device) {
    setBusy(true);
    try {
      if (device.endpoint === endpoint) {
        await unsubscribePush();
        setEndpoint(null);
      }
      await remove.mutateAsync(device.id);
    } catch (e) {
      notifyError(e, t("Entfernen fehlgeschlagen"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="wrap">
        <Group gap={6}>
          <IconDeviceMobile size={16} />
          <Text size="sm">{t("Push-Benachrichtigung aufs Handy oder den PC")}</Text>
        </Group>
        {support === "supported" &&
          (thisDevice ? (
            <Button size="xs" variant="default" color="red" onClick={() => void turnOff(thisDevice)} loading={busy}>
              {t("Auf diesem Gerät ausschalten")}
            </Button>
          ) : (
            <Button size="xs" leftSection={<IconBellRinging size={14} />} onClick={() => void turnOn()} loading={busy}>
              {t("Auf diesem Gerät einschalten")}
            </Button>
          ))}
      </Group>
      {support === "ios-needs-install" && (
        <Alert color="blue" variant="light">
          {t(
            "Auf dem iPhone/iPad gibt es Push nur für Apps auf dem Home-Bildschirm: in Safari „Teilen“ → „Zum Home-Bildschirm“, Famulus DMS von dort öffnen und hier einschalten (ab iOS 16.4).",
          )}
        </Alert>
      )}
      {support === "insecure" && (
        <Alert color="yellow" variant="light">
          {t(
            "Push geht nur über eine verschlüsselte Verbindung (https://), der dieses Gerät vertraut – siehe „Neues Gerät verbinden“ unten.",
          )}
        </Alert>
      )}
      {support === "unsupported" && (
        <Text size="sm" c="dimmed">
          {t("Dieser Browser unterstützt keine Push-Benachrichtigungen.")}
        </Text>
      )}

      {devices.length > 0 && (
        <Stack gap={6}>
          <Switch
            label={t("Push-Benachrichtigungen schicken")}
            checked={enabled}
            onChange={(e) => onToggle(e.currentTarget.checked)}
          />
          {devices.map((d) => (
            <Group key={d.id} justify="space-between" wrap="nowrap" data-testid="push-device">
              <div>
                <Group gap={6}>
                  <Text size="sm">{d.name}</Text>
                  {d.endpoint === endpoint && (
                    <Badge size="xs" variant="light">
                      {t("dieses Gerät")}
                    </Badge>
                  )}
                </Group>
                <Text size="xs" c={d.last_error ? "red" : "dimmed"}>
                  {d.last_error
                    ? t("Fehler: {{error}}", { error: d.last_error })
                    : d.last_success_at
                      ? t("zuletzt erreicht {{date}}", { date: formatDateTime(d.last_success_at) })
                      : t("seit {{date}}", { date: formatDateTime(d.created_at) })}
                </Text>
              </div>
              <Tooltip label={t("Push auf diesem Gerät beenden")}>
                <ActionIcon
                  variant="subtle"
                  color="red"
                  onClick={() => void turnOff(d)}
                  aria-label={t("{{name}} entfernen", { name: d.name })}
                >
                  <IconTrash size={16} />
                </ActionIcon>
              </Tooltip>
            </Group>
          ))}
          {enabled && (
            <Group>
              <Button size="xs" variant="default" onClick={onTest} loading={testing}>
                {t("Test-Push an alle Geräte")}
              </Button>
            </Group>
          )}
        </Stack>
      )}
    </Stack>
  );
}
