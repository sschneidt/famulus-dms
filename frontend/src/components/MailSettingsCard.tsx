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
import type { Schemas } from "../api/client";
import { useDeleteMailSettings, useMailSettings, useSaveMailSettings, useTestNotification } from "../api/queries";
import { formatDateTime } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

type Security = "starttls" | "ssl" | "none";

// Gaengige Anbieter - fuellen nur Server/Port/Verschluesselung vor
const PRESETS: Record<string, { host: string; port: number; security: Security; hint: string }> = {
  gmail: {
    host: "smtp.gmail.com",
    port: 587,
    security: "starttls",
    hint: "Gmail: App-Passwort verwenden (Google-Konto > Sicherheit, braucht Bestätigung in zwei Schritten).",
  },
  gmx: {
    host: "mail.gmx.net",
    port: 587,
    security: "starttls",
    hint: "GMX: In den Postfach-Einstellungen „POP3/IMAP Abruf“ bzw. Versand über externe Programme erlauben.",
  },
  webde: {
    host: "smtp.web.de",
    port: 587,
    security: "starttls",
    hint: "WEB.DE: In den Einstellungen „POP3/IMAP Abruf“ bzw. Versand über externe Programme erlauben.",
  },
  tonline: {
    host: "securesmtp.t-online.de",
    port: 465,
    security: "ssl",
    hint: "T-Online: eigenes E-Mail-Passwort (nicht das Kundencenter-Passwort) verwenden.",
  },
  icloud: {
    host: "smtp.mail.me.com",
    port: 587,
    security: "starttls",
    hint: "iCloud: App-spezifisches Passwort verwenden (account.apple.com).",
  },
};

const SECURITY = [
  { value: "starttls", label: "STARTTLS (meist Port 587)" },
  { value: "ssl", label: "SSL/TLS (meist Port 465)" },
  { value: "none", label: "keine (nur im Heimnetz)" },
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
        onSuccess: () => notifySuccess("E-Mail-Versand gespeichert – am besten gleich eine Test-E-Mail schicken"),
        onError: (e) => notifyError(e, "Speichern fehlgeschlagen"),
      },
    );
  }

  return (
    <Card withBorder radius="md" padding="lg">
      <Group gap="xs" mb={4}>
        <IconMail size={20} />
        <Title order={4}>E-Mail-Versand</Title>
      </Group>
      <Text size="sm" c="dimmed" mb="md">
        Über dieses Postfach verschickt HomeDMS die tägliche Erinnerung an alle, die E-Mail eingeschaltet haben. Am
        besten ein eigenes oder ohnehin vorhandenes Postfach mit App-Passwort. Das Passwort wird verschlüsselt
        gespeichert.
      </Text>
      {s?.last_error && (
        <Alert color="red" mb="md" title="Letzter Versand fehlgeschlagen">
          {s.last_error}
        </Alert>
      )}
      <Stack gap="sm">
        <Select
          label="Anbieter (füllt Server und Port aus)"
          placeholder="eigener Server"
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
            setHint(p?.hint ?? null);
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
            label="Server (SMTP)"
            value={form.host}
            onChange={(e) => set("host", e.currentTarget.value)}
            required
          />
          <NumberInput
            label="Port"
            value={form.port}
            min={1}
            max={65535}
            onChange={(v) => set("port", Number(v) || 587)}
            required
          />
          <Select
            label="Verschlüsselung"
            data={SECURITY}
            value={form.security}
            onChange={(v) => v && set("security", v as Security)}
            allowDeselect={false}
          />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput
            label="Benutzername"
            description="meist die E-Mail-Adresse"
            value={form.username}
            onChange={(e) => set("username", e.currentTarget.value)}
            autoComplete="off"
          />
          <PasswordInput
            label="Passwort"
            description={s?.password_set ? "gespeichert – leer lassen zum Behalten" : "am besten ein App-Passwort"}
            value={form.password}
            onChange={(e) => set("password", e.currentTarget.value)}
            autoComplete="new-password"
          />
          <TextInput
            label="Absender-Adresse"
            description="muss meist zum Postfach passen"
            value={form.sender}
            onChange={(e) => set("sender", e.currentTarget.value)}
            required
          />
          <TextInput
            label="Adresse von HomeDMS für Links"
            description="so, wie ihr HomeDMS im Browser öffnet"
            value={form.app_url}
            onChange={(e) => set("app_url", e.currentTarget.value)}
          />
        </SimpleGrid>
        <Group justify="space-between" mt="xs">
          <Text size="xs" c="dimmed">
            {s?.last_ok_at ? `Zuletzt erfolgreich: ${formatDateTime(s.last_ok_at)}` : ""}
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
                      title: "E-Mail-Versand entfernen?",
                      children: <Text size="sm">Erinnerungen kommen dann nur noch in der App und per Push.</Text>,
                      labels: { confirm: "Entfernen", cancel: "Abbrechen" },
                      confirmProps: { color: "red" },
                      onConfirm: () => remove.mutate(undefined, { onError: (e) => notifyError(e) }),
                    })
                  }
                >
                  Entfernen
                </Anchor>
                <Button
                  variant="default"
                  onClick={() =>
                    test.mutate("email", {
                      onSuccess: (r) =>
                        r.ok ? notifySuccess(r.message) : notifyError(new Error(r.message), "Test fehlgeschlagen"),
                      onError: (e) => notifyError(e, "Test fehlgeschlagen"),
                    })
                  }
                  loading={test.isPending}
                >
                  Test-E-Mail an mich
                </Button>
              </>
            )}
            <Button onClick={submit} loading={save.isPending} disabled={!form.host || !form.sender}>
              Speichern
            </Button>
          </Group>
        </Group>
      </Stack>
    </Card>
  );
}
