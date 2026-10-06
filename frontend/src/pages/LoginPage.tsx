import {
  Alert,
  Anchor,
  Button,
  Center,
  Loader,
  MultiSelect,
  Paper,
  PasswordInput,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconAlertCircle, IconLockOpen, IconShieldLock } from "@tabler/icons-react";
import { useState, type FormEvent } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router";
import { api, call } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Logo } from "../components/Logo";
import { LANGUAGES, chooseLanguageBeforeLogin, currentLanguage, isLanguage } from "../i18n";
import { insecureConnection, useSetupStatus } from "../lib/connection";
import { notifySuccess } from "../lib/notify";

/**
 * Anmeldung - oder, solange noch kein Haushalt angelegt ist, die Ersteinrichtung
 * (Haushalt + erstes Admin-Konto, POST /setup/bootstrap).
 */
export function LoginPage() {
  const { state } = useAuth();
  const location = useLocation();
  const setup = useSetupStatus();
  const { t, i18n } = useTranslation();

  if (state.status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  return (
    <Center mih="100vh" p="md">
      <Paper withBorder shadow="sm" p="xl" w="100%" maw={420}>
        <Stack>
          <Center>
            <Logo size="xl" />
          </Center>
          <SegmentedControl
            size="xs"
            data={LANGUAGES.map((l) => ({ value: l.code, label: l.label }))}
            value={isLanguage(i18n.language) ? i18n.language : "de"}
            onChange={(v) => isLanguage(v) && void chooseLanguageBeforeLogin(v)}
            aria-label={t("Sprache")}
          />
          {insecureConnection() && (
            <Alert color="orange" icon={<IconLockOpen />} title={t("Verbindung nicht verschlüsselt")}>
              {t(
                "Passwort und Dokumente gehen im Klartext durchs Netz. Famulus DMS über https:// aufrufen – oder den Reverse Proxy mit HTTPS verwenden.",
              )}
            </Alert>
          )}
          {setup.isPending || state.status === "loading" ? (
            <Center py="lg">
              <Loader />
            </Center>
          ) : setup.isError ? (
            <Alert color="red" icon={<IconAlertCircle />} title={t("Server nicht erreichbar")}>
              {setup.error.message}
              <Anchor component="button" display="block" mt="xs" onClick={() => setup.refetch()}>
                {t("Erneut versuchen")}
              </Anchor>
            </Alert>
          ) : setup.data.bootstrapped === false ? (
            <SetupForm onDone={() => setup.refetch()} />
          ) : (
            <LoginForm />
          )}
        </Stack>
      </Paper>
    </Center>
  );
}

function LoginForm() {
  const { login } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [challenge, setChallenge] = useState<string | null>(null);
  const done = (notice?: string | null) => {
    if (notice) notifySuccess(notice);
    const from = (location.state as { from?: string } | null)?.from ?? "/";
    navigate(from, { replace: true });
  };
  const form = useForm({
    initialValues: { email: "", password: "" },
    validate: {
      email: (v) => (v.trim() ? null : t("Bitte E-Mail-Adresse eingeben")),
      password: (v) => (v ? null : t("Bitte Passwort eingeben")),
    },
  });

  const submit = form.onSubmit(async (values) => {
    setError(null);
    try {
      const result = await login(values.email.trim(), values.password);
      if (result.status === "two-factor") setChallenge(result.challenge);
      else done(result.notice);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : t("Anmeldung fehlgeschlagen"));
    }
  });

  if (challenge) return <TwoFactorForm challenge={challenge} onDone={done} onRestart={() => setChallenge(null)} />;

  return (
    <form onSubmit={submit}>
      <Stack>
        <Title order={3} ta="center">
          {t("Anmelden")}
        </Title>
        {error && (
          <Alert color="red" icon={<IconAlertCircle />}>
            {error}
          </Alert>
        )}
        <TextInput
          label={t("E-Mail")}
          type="email"
          autoComplete="username"
          autoFocus
          {...form.getInputProps("email")}
        />
        <PasswordInput label={t("Passwort")} autoComplete="current-password" {...form.getInputProps("password")} />
        <Button type="submit" loading={form.submitting} fullWidth>
          {t("Anmelden")}
        </Button>
        <Text size="xs" c="dimmed" ta="center">
          <Trans
            i18nKey="Passwort vergessen? Ein Admin setzt es unter „Benutzer“ zurück (oder auf dem Server mit <code>python -m homedms.cli reset-password</code>)."
            components={{ code: <code /> }}
          />
        </Text>
      </Stack>
    </form>
  );
}

/** Zweiter Schritt: 6-stelliger Code aus der Authenticator-App oder ein Wiederherstellungscode. */
function TwoFactorForm({
  challenge,
  onDone,
  onRestart,
}: {
  challenge: string;
  onDone(notice: string | null): void;
  onRestart(): void;
}) {
  const { completeTwoFactor } = useAuth();
  const { t } = useTranslation();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(await completeTwoFactor(challenge, code.trim()));
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : t("Code nicht akzeptiert"));
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)}>
      <Stack>
        <Title order={3} ta="center">
          {t("Bestätigungscode")}
        </Title>
        <Text size="sm" c="dimmed" ta="center">
          {t("Code aus der Authenticator-App eingeben – oder einen Wiederherstellungscode, falls das Handy fehlt.")}
        </Text>
        {error && (
          <Alert color="red" icon={<IconAlertCircle />}>
            {error}
          </Alert>
        )}
        <TextInput
          label={t("Code")}
          leftSection={<IconShieldLock size={16} />}
          value={code}
          onChange={(e) => setCode(e.currentTarget.value)}
          autoComplete="one-time-code"
          inputMode="text"
          autoFocus
          maxLength={20}
        />
        <Button type="submit" loading={busy} disabled={code.replace(/\W/g, "").length < 6} fullWidth>
          {t("Bestätigen")}
        </Button>
        <Anchor component="button" type="button" size="sm" ta="center" onClick={onRestart}>
          {t("Zurück zur Anmeldung")}
        </Anchor>
      </Stack>
    </form>
  );
}

// Vorschlag fuer die Texterkennung: Sprache der Oberflaeche + Deutsch + Englisch
const UI_TO_OCR: Record<string, string> = { de: "deu", en: "eng", ru: "rus" };
const defaultOcr = (lang: string) => [...new Set([UI_TO_OCR[lang] ?? "deu", "deu", "eng"])];

function SetupForm({ onDone }: { onDone: () => void }) {
  const { login } = useAuth();
  const { t, i18n } = useTranslation();
  const setup = useSetupStatus();
  const catalog = setup.data?.ocr_languages ?? [];
  const [ocr, setOcr] = useState<string[] | null>(null); // null = Vorschlag passend zur Sprache
  const ocrSelection = ocr ?? defaultOcr(i18n.language);
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: { code: "", household: "", name: "", email: "", password: "", repeat: "" },
    validate: {
      code: (v) => (v.trim() ? null : t("Bitte den Einrichtungscode eingeben")),
      household: (v) => (v.trim() ? null : t("Bitte einen Namen für den Haushalt angeben")),
      name: (v) => (v.trim() ? null : t("Bitte Ihren Namen angeben")),
      email: (v) => (/^\S+@\S+\.\S+$/.test(v.trim()) ? null : t("Bitte eine gültige E-Mail-Adresse angeben")),
      password: (v) => (v.length >= 8 ? null : t("Mindestens 8 Zeichen")),
      repeat: (v, values) => (v === values.password ? null : t("Passwörter stimmen nicht überein")),
    },
  });

  const submit = form.onSubmit(async (values) => {
    setError(null);
    try {
      await call(
        api.POST("/api/v1/setup/bootstrap", {
          body: {
            household_name: values.household.trim(),
            default_language: currentLanguage(),
            admin_display_name: values.name.trim(),
            admin_email: values.email.trim(),
            admin_password: values.password,
            setup_code: values.code.trim(),
            ocr_languages: ocrSelection,
          },
        }),
      );
      await login(values.email.trim(), values.password);
      onDone();
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : t("Einrichtung fehlgeschlagen"));
    }
  });

  return (
    <form onSubmit={submit}>
      <Stack>
        <div>
          <Title order={3} ta="center">
            {t("Ersteinrichtung")}
          </Title>
          <Text size="sm" c="dimmed" ta="center">
            {t("Legen Sie Ihren Haushalt und das erste Admin-Konto an.")}
          </Text>
        </div>
        {error && (
          <Alert color="red" icon={<IconAlertCircle />}>
            {error}
          </Alert>
        )}
        <TextInput
          label={t("Einrichtungscode")}
          description={t(
            "Steht im Protokoll des Servers (Docker: docker compose logs app-api), in der Ausgabe des Installationsskripts bzw. in der Datei .einrichtungscode im Dokumente-Ordner",
          )}
          placeholder="XXXX-XXXX-XXXX"
          autoComplete="off"
          {...form.getInputProps("code")}
        />
        <TextInput
          label={t("Name des Haushalts")}
          placeholder={t("z. B. Familie Muster")}
          {...form.getInputProps("household")}
        />
        <TextInput label={t("Ihr Name")} autoComplete="name" {...form.getInputProps("name")} />
        <TextInput label={t("E-Mail")} type="email" autoComplete="username" {...form.getInputProps("email")} />
        <PasswordInput label={t("Passwort")} autoComplete="new-password" {...form.getInputProps("password")} />
        <PasswordInput
          label={t("Passwort wiederholen")}
          autoComplete="new-password"
          {...form.getInputProps("repeat")}
        />
        {catalog.length > 0 && (
          <MultiSelect
            label={t("Sprachen Ihrer Dokumente")}
            description={t(
              "Für die Texterkennung. Fehlende Sprachpakete lädt Famulus DMS nach der Einrichtung selbst herunter; ändern lässt sich das später unter „Sprachen“.",
            )}
            data={catalog.map((c) => ({ value: c.code, label: c.name }))}
            value={ocrSelection}
            onChange={setOcr}
            searchable
            hidePickedOptions
          />
        )}
        <Button type="submit" loading={form.submitting} fullWidth>
          {t("Haushalt anlegen")}
        </Button>
      </Stack>
    </form>
  );
}
