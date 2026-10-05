import {
  Alert,
  Anchor,
  Button,
  Card,
  Group,
  Loader,
  NumberInput,
  PasswordInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconMail } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { useDeleteMailSettings, useMailSettings, useSaveMailSettings, useTestNotification } from "../api/queries";
import { formatDateTime, tk } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

type Security = "starttls" | "ssl" | "none";

// Gaengige Anbieter - fuellen nur Server/Port/Verschluesselung vor
const PRESETS: Record<string, { host: string; port: number; security: Security; hint: string }> = {
  gmail: {
    host: "smtp.gmail.com",
    port: 587,
    security: "starttls",
    hint: tk("Gmail: App-Passwort verwenden (Google-Konto > Sicherheit, braucht Bestätigung in zwei Schritten)."),
  },
  gmx: {
    host: "mail.gmx.net",
    port: 587,
    security: "starttls",
    hint: tk("GMX: In den Postfach-Einstellungen „POP3/IMAP Abruf“ bzw. Versand über externe Programme erlauben."),
  },
  webde: {
    host: "smtp.web.de",
    port: 587,
    security: "starttls",
    hint: tk("WEB.DE: In den Einstellungen „POP3/IMAP Abruf“ bzw. Versand über externe Programme erlauben."),
  },
  tonline: {
    host: "securesmtp.t-online.de",
    port: 465,
    security: "ssl",
    hint: tk("T-Online: eigenes E-Mail-Passwort (nicht das Kundencenter-Passwort) verwenden."),
  },
  icloud: {
    host: "smtp.mail.me.com",
    port: 587,
    security: "starttls",
    hint: tk("iCloud: App-spezifisches Passwort verwenden (account.apple.com)."),
  },
};

const SECURITY = [
  { value: "starttls", label: tk("STARTTLS (meist Port 587)") },
  { value: "ssl", label: tk("SSL/TLS (meist Port 465)") },
  { value: "none", label: tk("keine (nur im Heimnetz)") },
];

interface Form {
  host: string;
  port: number;
  security: Security;
  username: string;
  password: string;
  sender: string;
  app_url: string;
}

function toForm(s: Schemas["MailSettings"] | undefined): Form {
  return {
    host: s?.host ?? "",
    port: s?.port ?? 587,
    security: (s?.security as Security | undefined) ?? "starttls",
    username: s?.username ?? "",
    password: "",
    sender: s?.sender ?? "",
    app_url: s?.app_url || window.location.origin,
  };
}

/** Seite "Benutzer" (Admin): Postfach, ueber das HomeDMS die Erinnerungen verschickt. */
export function MailSettingsCard() {
  const settings = useMailSettings(true);
  if (settings.isError) return <Alert color="red">{settings.error.message}</Alert>;
  if (!settings.data) return <Loader size="sm" />;
  // neu gespeichert -> Formular mit den gespeicherten Werten neu aufbauen
  return <MailSettingsForm key={JSON.stringify(settings.data)} s={settings.data} />;
}

function MailSettingsForm({ s }: { s: Schemas["MailSettings"] }) {
  const { t } = useTranslation();
  const save = useSaveMailSettings();
  const remove = useDeleteMailSettings();
  const test = useTestNotification();
  const [form, setForm] = useState<Form>(() => toForm(s));
  const [hint, setHint] = useState<string | null>(null);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));

  function submit() {
    save.mutate(
      { ...form, password: form.password ? form.password : s?.password_set ? null : "" },
      {
        onSuccess: () => notifySuccess(t("E-Mail-Versand gespeichert – am besten gleich eine Test-E-Mail schicken")),
        onError: (e) => notifyError(e, t("Speichern fehlgeschlagen")),
      },
    );
  }

  return (
    <Card withBorder radius="md" padding="lg">
      <Group gap="xs" mb={4}>
        <IconMail size={20} />
        <Title order={4}>{t("E-Mail-Versand")}</Title>
      </Group>
      <Text size="sm" c="dimmed" mb="md">
        {t(
          "Über dieses Postfach verschickt HomeDMS die tägliche Erinnerung an alle, die E-Mail eingeschaltet haben. Am besten ein eigenes oder ohnehin vorhandenes Postfach mit App-Passwort. Das Passwort wird verschlüsselt gespeichert.",
        )}
      </Text>
      {s?.last_error && (
        <Alert color="red" mb="md" title={t("Letzter Versand fehlgeschlagen")}>
          {s.last_error}
        </Alert>
      )}
      <Stack gap="sm">
        <Select
          label={t("Anbieter (füllt Server und Port aus)")}
          placeholder={t("eigener Server")}
          data={[
            { value: "gmail", label: "Gmail" },
            { value: "gmx", label: "GMX" },
            { value: "webde", label: "WEB.DE" },
            { value: "tonline", label: "T-Online" },
            { value: "icloud", label: "iCloud" },
          ]}
          clearable
          onChange={(v) => {
            const p = v ? PRESETS[v] : undefined;
            setHint(p ? t(p.hint) : null);
            if (p) setForm((f) => ({ ...f, host: p.host, port: p.port, security: p.security }));
          }}
          maw={320}
        />
        {hint && (
          <Text size="sm" c="blue">
            {hint}
          </Text>
        )}
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <TextInput
            label={t("Server (SMTP)")}
            value={form.host}
            onChange={(e) => set("host", e.currentTarget.value)}
            required
          />
          <NumberInput
            label={t("Port")}
            value={form.port}
            min={1}
            max={65535}
            onChange={(v) => set("port", Number(v) || 587)}
            required
          />
          <Select
            label={t("Verschlüsselung")}
            data={SECURITY.map((o) => ({ ...o, label: t(o.label) }))}
            value={form.security}
            onChange={(v) => v && set("security", v as Security)}
            allowDeselect={false}
          />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput
            label={t("Benutzername")}
            description={t("meist die E-Mail-Adresse")}
            value={form.username}
            onChange={(e) => set("username", e.currentTarget.value)}
            autoComplete="off"
          />
          <PasswordInput
            label={t("Passwort")}
            description={
              s?.password_set ? t("gespeichert – leer lassen zum Behalten") : t("am besten ein App-Passwort")
            }
            value={form.password}
            onChange={(e) => set("password", e.currentTarget.value)}
            autoComplete="new-password"
          />
          <TextInput
            label={t("Absender-Adresse")}
            description={t("muss meist zum Postfach passen")}
            value={form.sender}
            onChange={(e) => set("sender", e.currentTarget.value)}
            required
          />
          <TextInput
            label={t("Adresse von HomeDMS für Links")}
            description={t("so, wie ihr HomeDMS im Browser öffnet")}
            value={form.app_url}
            onChange={(e) => set("app_url", e.currentTarget.value)}
          />
        </SimpleGrid>
        <Group justify="space-between" mt="xs">
          <Text size="xs" c="dimmed">
            {s?.last_ok_at ? t("Zuletzt erfolgreich: {{date}}", { date: formatDateTime(s.last_ok_at) }) : ""}
          </Text>
          <Group gap="xs">
            {s?.configured && (
              <>
                <Anchor
                  component="button"
                  size="sm"
                  c="red"
                  onClick={() =>
                    modals.openConfirmModal({
                      title: t("E-Mail-Versand entfernen?"),
                      children: (
                        <Text size="sm">{t("Erinnerungen kommen dann nur noch in der App und per Push.")}</Text>
                      ),
                      labels: { confirm: t("Entfernen"), cancel: t("Abbrechen") },
                      confirmProps: { color: "red" },
                      onConfirm: () => remove.mutate(undefined, { onError: (e) => notifyError(e) }),
                    })
                  }
                >
                  {t("Entfernen")}
                </Anchor>
                <Button
                  variant="default"
                  onClick={() =>
                    test.mutate("email", {
                      onSuccess: (r) =>
                        r.ok ? notifySuccess(r.message) : notifyError(new Error(r.message), t("Test fehlgeschlagen")),
                      onError: (e) => notifyError(e, t("Test fehlgeschlagen")),
                    })
                  }
                  loading={test.isPending}
                >
                  {t("Test-E-Mail an mich")}
                </Button>
              </>
            )}
            <Button onClick={submit} loading={save.isPending} disabled={!form.host || !form.sender}>
              {t("Speichern")}
            </Button>
          </Group>
        </Group>
      </Stack>
    </Card>
  );
}
