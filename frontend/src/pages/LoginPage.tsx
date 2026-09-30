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
import { IconAlertCircle } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { api, call } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Logo } from "../components/Logo";

/**
 * Anmeldung - oder, solange noch kein Haushalt angelegt ist, die Ersteinrichtung
 * (Haushalt + erstes Admin-Konto, POST /setup/bootstrap).
 */
export function LoginPage() {
  const { state } = useAuth();
  const location = useLocation();
  const setup = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => call(api.GET("/api/v1/setup/status")) as Promise<{ bootstrapped?: boolean }>,
  });

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
      await login(values.email.trim(), values.password);
      const from = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Anmeldung fehlgeschlagen");
    }
  });

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
          Passwort vergessen? Ein Admin kann es mit <code>homedms reset-password</code> neu setzen.
        </Text>
      </Stack>
    </form>
  );
}

function SetupForm({ onDone }: { onDone: () => void }) {
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: { household: "", name: "", email: "", password: "", repeat: "" },
    validate: {
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
