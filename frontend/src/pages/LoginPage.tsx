import {
  Alert,
  Anchor,
  Button,
  Center,
  Loader,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconAlertCircle, IconLockOpen, IconShieldLock } from "@tabler/icons-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { api, call } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Logo } from "../components/Logo";
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
          {insecureConnection() && (
            <Alert color="orange" icon={<IconLockOpen />} title="Verbindung nicht verschlüsselt">
              Passwort und Dokumente gehen im Klartext durchs Netz. HomeDMS über https:// aufrufen – oder den Reverse
              Proxy mit HTTPS verwenden.
            </Alert>
          )}
          {setup.isPending || state.status === "loading" ? (
            <Center py="lg">
              <Loader />
            </Center>
          ) : setup.isError ? (
            <Alert color="red" icon={<IconAlertCircle />} title="Server nicht erreichbar">
              {setup.error.message}
              <Anchor component="button" display="block" mt="xs" onClick={() => setup.refetch()}>
                Erneut versuchen
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
      email: (v) => (v.trim() ? null : "Bitte E-Mail-Adresse eingeben"),
      password: (v) => (v ? null : "Bitte Passwort eingeben"),
    },
  });

  const submit = form.onSubmit(async (values) => {
    setError(null);
    try {
      const result = await login(values.email.trim(), values.password);
      if (result.status === "two-factor") setChallenge(result.challenge);
      else done(result.notice);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Anmeldung fehlgeschlagen");
    }
  });

  if (challenge) return <TwoFactorForm challenge={challenge} onDone={done} onRestart={() => setChallenge(null)} />;

  return (
    <form onSubmit={submit}>
      <Stack>
        <Title order={3} ta="center">
          Anmelden
        </Title>
        {error && (
          <Alert color="red" icon={<IconAlertCircle />}>
            {error}
          </Alert>
        )}
        <TextInput label="E-Mail" type="email" autoComplete="username" autoFocus {...form.getInputProps("email")} />
        <PasswordInput label="Passwort" autoComplete="current-password" {...form.getInputProps("password")} />
        <Button type="submit" loading={form.submitting} fullWidth>
          Anmelden
        </Button>
        <Text size="xs" c="dimmed" ta="center">
          Passwort vergessen? Ein Admin setzt es unter „Benutzer“ zurück (oder auf dem Server mit{" "}
          <code>python -m homedms.cli reset-password</code>).
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
      setError(err instanceof Error && err.message ? err.message : "Code nicht akzeptiert");
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)}>
      <Stack>
        <Title order={3} ta="center">
          Bestätigungscode
        </Title>
        <Text size="sm" c="dimmed" ta="center">
          Code aus der Authenticator-App eingeben – oder einen Wiederherstellungscode, falls das Handy fehlt.
        </Text>
        {error && (
          <Alert color="red" icon={<IconAlertCircle />}>
            {error}
          </Alert>
        )}
        <TextInput
          label="Code"
          leftSection={<IconShieldLock size={16} />}
          value={code}
          onChange={(e) => setCode(e.currentTarget.value)}
          autoComplete="one-time-code"
          inputMode="text"
          autoFocus
          maxLength={20}
        />
        <Button type="submit" loading={busy} disabled={code.replace(/\W/g, "").length < 6} fullWidth>
          Bestätigen
        </Button>
        <Anchor component="button" type="button" size="sm" ta="center" onClick={onRestart}>
          Zurück zur Anmeldung
        </Anchor>
      </Stack>
    </form>
  );
}

function SetupForm({ onDone }: { onDone: () => void }) {
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: { code: "", household: "", name: "", email: "", password: "", repeat: "" },
    validate: {
      code: (v) => (v.trim() ? null : "Bitte den Einrichtungscode eingeben"),
      household: (v) => (v.trim() ? null : "Bitte einen Namen für den Haushalt angeben"),
      name: (v) => (v.trim() ? null : "Bitte Ihren Namen angeben"),
      email: (v) => (/^\S+@\S+\.\S+$/.test(v.trim()) ? null : "Bitte eine gültige E-Mail-Adresse angeben"),
      password: (v) => (v.length >= 8 ? null : "Mindestens 8 Zeichen"),
      repeat: (v, values) => (v === values.password ? null : "Passwörter stimmen nicht überein"),
    },
  });

  const submit = form.onSubmit(async (values) => {
    setError(null);
    try {
      await call(
        api.POST("/api/v1/setup/bootstrap", {
          body: {
            household_name: values.household.trim(),
            default_language: "de",
            admin_display_name: values.name.trim(),
            admin_email: values.email.trim(),
            admin_password: values.password,
            setup_code: values.code.trim(),
          },
        }),
      );
      await login(values.email.trim(), values.password);
      onDone();
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Einrichtung fehlgeschlagen");
    }
  });

  return (
    <form onSubmit={submit}>
      <Stack>
        <div>
          <Title order={3} ta="center">
            Ersteinrichtung
          </Title>
          <Text size="sm" c="dimmed" ta="center">
            Legen Sie Ihren Haushalt und das erste Admin-Konto an.
          </Text>
        </div>
        {error && (
          <Alert color="red" icon={<IconAlertCircle />}>
            {error}
          </Alert>
        )}
        <TextInput
          label="Einrichtungscode"
          description="Steht im Protokoll des Servers (Docker: docker compose logs app-api), in der Ausgabe des Installationsskripts bzw. in der Datei .einrichtungscode im Dokumente-Ordner"
          placeholder="XXXX-XXXX-XXXX"
          autoComplete="off"
          {...form.getInputProps("code")}
        />
        <TextInput label="Name des Haushalts" placeholder="z. B. Familie Muster" {...form.getInputProps("household")} />
        <TextInput label="Ihr Name" autoComplete="name" {...form.getInputProps("name")} />
        <TextInput label="E-Mail" type="email" autoComplete="username" {...form.getInputProps("email")} />
        <PasswordInput label="Passwort" autoComplete="new-password" {...form.getInputProps("password")} />
        <PasswordInput label="Passwort wiederholen" autoComplete="new-password" {...form.getInputProps("repeat")} />
        <Button type="submit" loading={form.submitting} fullWidth>
          Haushalt anlegen
        </Button>
      </Stack>
    </form>
  );
}
