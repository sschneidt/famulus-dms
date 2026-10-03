import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Code,
  CopyButton,
  Group,
  Loader,
  Modal,
  PasswordInput,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import {
  IconCheck,
  IconCopy,
  IconDeviceDesktop,
  IconDeviceMobile,
  IconLogout,
  IconShieldCheck,
  IconShieldOff,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call, type Schemas } from "../api/client";
import { useAuth, useUser } from "../auth/AuthContext";
import { certificatePageUrl, useSetupStatus } from "../lib/connection";
import { formatDateTime } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

/**
 * Konto & Sicherheit: Name (und Haushaltsname fuer Admins), Passwort, Zwei-Faktor-Anmeldung,
 * angemeldete Geraete und wie ein neues Geraet der Verschluesselung vertraut.
 */
export function AccountPage() {
  return (
    <Stack maw={900}>
      <Title order={2}>Konto & Sicherheit</Title>
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Section title="Profil">
          <ProfileForm />
        </Section>
        <Section title="Passwort">
          <PasswordForm />
        </Section>
      </SimpleGrid>
      <Section title="Zwei-Faktor-Anmeldung">
        <TwoFactorSection />
      </Section>
      <Section title="Angemeldete Geräte">
        <SessionsSection />
      </Section>
      <NewDeviceHint />
    </Stack>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card withBorder radius="md" padding="lg">
      <Title order={4} mb="sm">
        {title}
      </Title>
      {children}
    </Card>
  );
}

function ProfileForm() {
  const user = useUser();
  const { refresh } = useAuth();
  const isAdmin = user.role === "admin";
  const [displayName, setDisplayName] = useState(user.display_name);
  const [household, setHousehold] = useState(user.household_name ?? "");
  const [saving, setSaving] = useState(false);

  const nameChanged = displayName.trim() !== user.display_name;
  const householdChanged = isAdmin && household.trim() !== (user.household_name ?? "");
  const valid = displayName.trim() !== "" && (!isAdmin || household.trim() !== "");

  async function save() {
    setSaving(true);
    try {
      if (nameChanged) {
        await call(api.PATCH("/api/v1/auth/me", { body: { display_name: displayName.trim() } }));
      }
      if (householdChanged) {
        const result = await call(api.PATCH("/api/v1/tenant", { body: { name: household.trim() } }));
        if (result.documents_refiled) {
          notifySuccess(`Haushalt umbenannt – ${result.documents_refiled} Dokument(e) ziehen in den neuen Ordner um.`);
        }
      }
      await refresh();
      if (nameChanged && !householdChanged) notifySuccess("Name gespeichert");
    } catch (e) {
      notifyError(e, "Speichern fehlgeschlagen");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack>
      <TextInput
        label="Dein Name"
        value={displayName}
        onChange={(e) => setDisplayName(e.currentTarget.value)}
        error={displayName.trim() === "" ? "Bitte einen Namen angeben" : undefined}
      />
      <TextInput label="E-Mail" value={user.email} disabled />
      {isAdmin && (
        <TextInput
          label="Name des Haushalts"
          description="Zugleich der oberste Ordner in der Ablage – beim Ändern werden die Dateien verschoben"
          value={household}
          onChange={(e) => setHousehold(e.currentTarget.value)}
          error={household.trim() === "" ? "Bitte einen Namen angeben" : undefined}
        />
      )}
      <Group justify="flex-end">
        <Button onClick={() => void save()} loading={saving} disabled={!valid || (!nameChanged && !householdChanged)}>
          Speichern
        </Button>
      </Group>
    </Stack>
  );
}

/** Eigenes Passwort aendern - dieses Geraet bleibt angemeldet, alle anderen werden abgemeldet. */
function PasswordForm() {
  const queryClient = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [saving, setSaving] = useState(false);
  const mismatch = repeat !== "" && repeat !== next;
  const valid = current !== "" && next.length >= 8 && next === repeat;

  async function change() {
    setSaving(true);
    try {
      await call(api.PUT("/api/v1/auth/password", { body: { current_password: current, new_password: next } }));
      notifySuccess("Passwort geändert – alle anderen Geräte sind abgemeldet");
      setCurrent("");
      setNext("");
      setRepeat("");
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    } catch (e) {
      notifyError(e, "Passwort nicht geändert");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack gap="xs">
      <PasswordInput label="Bisheriges Passwort" value={current} onChange={(e) => setCurrent(e.currentTarget.value)} />
      <PasswordInput
        label="Neues Passwort"
        description="Mindestens 8 Zeichen – besser ein ganzer Satz"
        value={next}
        onChange={(e) => setNext(e.currentTarget.value)}
        error={next.length > 0 && next.length < 8 ? "Mindestens 8 Zeichen" : undefined}
      />
      <PasswordInput
        label="Neues Passwort wiederholen"
        value={repeat}
        onChange={(e) => setRepeat(e.currentTarget.value)}
        error={mismatch ? "Stimmt nicht überein" : undefined}
      />
      <Group justify="flex-end">
        <Button onClick={() => void change()} loading={saving} disabled={!valid}>
          Passwort ändern
        </Button>
      </Group>
    </Stack>
  );
}

// --- Zwei-Faktor ---------------------------------------------------------------------------------

function TwoFactorSection() {
  const { refresh } = useAuth();
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["two-factor"], queryFn: () => call(api.GET("/api/v1/auth/2fa")) });
  const [dialog, setDialog] = useState<"setup" | "disable" | "codes" | null>(null);
  const reload = () => {
    void queryClient.invalidateQueries({ queryKey: ["two-factor"] });
    void refresh();
  };

  if (status.isPending) return <Loader size="sm" />;
  if (status.isError) return <Alert color="red">{status.error.message}</Alert>;
  const enabled = status.data.enabled;

  return (
    <Stack gap="sm">
      <Group gap="xs">
        <Badge
          color={enabled ? "green" : "gray"}
          variant="light"
          leftSection={enabled ? <IconShieldCheck size={14} /> : <IconShieldOff size={14} />}
        >
          {enabled ? "Eingeschaltet" : "Ausgeschaltet"}
        </Badge>
        {enabled && (
          <Text size="sm" c={status.data.recovery_codes_left <= 2 ? "orange" : "dimmed"}>
            noch {status.data.recovery_codes_left} Wiederherstellungscodes
          </Text>
        )}
      </Group>
      <Text size="sm" c="dimmed">
        Nach dem Passwort fragt HomeDMS zusätzlich nach einem Code aus einer Authenticator-App (z. B. Google oder
        Microsoft Authenticator, Aegis, 2FAS). Wer nur dein Passwort kennt, kommt so nicht hinein.
      </Text>
      <Group>
        {enabled ? (
          <>
            <Button variant="light" onClick={() => setDialog("codes")}>
              Neue Wiederherstellungscodes
            </Button>
            <Button variant="subtle" color="red" onClick={() => setDialog("disable")}>
              Ausschalten
            </Button>
          </>
        ) : (
          <Button leftSection={<IconShieldCheck size={16} />} onClick={() => setDialog("setup")}>
            Einrichten
          </Button>
        )}
      </Group>
      <Modal
        opened={dialog === "setup"}
        onClose={() => setDialog(null)}
        title="Zwei-Faktor-Anmeldung einrichten"
        size="lg"
      >
        {dialog === "setup" && (
          <SetupTwoFactor
            onDone={() => {
              setDialog(null);
              reload();
            }}
          />
        )}
      </Modal>
      <Modal opened={dialog === "disable"} onClose={() => setDialog(null)} title="Zwei-Faktor-Anmeldung ausschalten">
        {dialog === "disable" && (
          <PasswordStep
            action="Ausschalten"
            color="red"
            text="Danach genügt wieder das Passwort allein."
            run={(password) => call(api.POST("/api/v1/auth/2fa/disable", { body: { password } }))}
            onDone={() => {
              notifySuccess("Zwei-Faktor-Anmeldung ausgeschaltet");
              setDialog(null);
              reload();
            }}
          />
        )}
      </Modal>
      <Modal opened={dialog === "codes"} onClose={() => setDialog(null)} title="Neue Wiederherstellungscodes" size="lg">
        {dialog === "codes" && <NewRecoveryCodes onDone={() => setDialog(null)} reload={reload} />}
      </Modal>
    </Stack>
  );
}

function PasswordStep({
  action,
  text,
  color,
  run,
  onDone,
}: {
  action: string;
  text: string;
  color?: string;
  run(password: string): Promise<unknown>;
  onDone(result: unknown): void;
}) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setBusy(true);
        run(password)
          .then(onDone, (err) => notifyError(err, `${action} nicht möglich`))
          .finally(() => setBusy(false));
      }}
    >
      <Stack>
        <Text size="sm">{text}</Text>
        <PasswordInput
          label="Zur Sicherheit: dein Passwort"
          value={password}
          onChange={(e) => setPassword(e.currentTarget.value)}
          data-autofocus
        />
        <Group justify="flex-end">
          <Button type="submit" color={color} loading={busy} disabled={!password}>
            {action}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function SetupTwoFactor({ onDone }: { onDone(): void }) {
  const [setup, setSetup] = useState<Schemas["TwoFactorSetup"] | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const enable = useMutation({
    mutationFn: () => call(api.POST("/api/v1/auth/2fa/enable", { body: { code: code.trim() } })),
    onSuccess: (r) => setCodes(r.recovery_codes),
    onError: (e) => notifyError(e, "Code nicht akzeptiert"),
  });

  if (!setup) {
    return (
      <PasswordStep
        action="Weiter"
        text="Du brauchst eine Authenticator-App auf dem Handy. Im nächsten Schritt scannst du damit einen QR-Code."
        run={(password) => call(api.POST("/api/v1/auth/2fa/setup", { body: { password } }))}
        onDone={(r) => setSetup(r as Schemas["TwoFactorSetup"])}
      />
    );
  }
  if (codes) {
    return (
      <Stack>
        <Alert color="green" icon={<IconCheck />} title="Zwei-Faktor-Anmeldung ist eingeschaltet">
          Bewahre diese Wiederherstellungscodes sicher auf (ausdrucken oder im Passwort-Manager). Jeder Code
          funktioniert einmal, falls das Handy verloren geht. Sie werden nur jetzt angezeigt.
        </Alert>
        <RecoveryCodeList codes={codes} />
        <Group justify="flex-end">
          <Button onClick={onDone}>Ich habe die Codes gesichert</Button>
        </Group>
      </Stack>
    );
  }
  return (
    <Stack>
      <Text size="sm">1. QR-Code mit der Authenticator-App scannen:</Text>
      <Center>
        {/* SVG kommt vom eigenen Server (segno), enthaelt keine Skripte */}
        <Box
          w={220}
          h={220}
          bg="white"
          style={{ borderRadius: 8 }}
          dangerouslySetInnerHTML={{ __html: setup.qr_svg }}
          data-testid="qr"
        />
      </Center>
      <Text size="xs" c="dimmed" ta="center">
        Kein Scannen möglich? Schlüssel von Hand eingeben: <Code>{setup.secret}</Code>
      </Text>
      <TextInput
        label="2. Den 6-stelligen Code aus der App eingeben"
        value={code}
        onChange={(e) => setCode(e.currentTarget.value)}
        autoComplete="one-time-code"
        inputMode="numeric"
        maxLength={7}
      />
      <Group justify="flex-end">
        <Button
          onClick={() => enable.mutate()}
          loading={enable.isPending}
          disabled={code.replace(/\D/g, "").length !== 6}
        >
          Bestätigen
        </Button>
      </Group>
    </Stack>
  );
}

function NewRecoveryCodes({ onDone, reload }: { onDone(): void; reload(): void }) {
  const [codes, setCodes] = useState<string[] | null>(null);
  if (!codes) {
    return (
      <PasswordStep
        action="Neue Codes erzeugen"
        text="Die bisherigen Wiederherstellungscodes werden dabei ungültig."
        run={(password) => call(api.POST("/api/v1/auth/2fa/recovery-codes", { body: { password } }))}
        onDone={(r) => {
          setCodes((r as Schemas["RecoveryCodes"]).recovery_codes);
          reload();
        }}
      />
    );
  }
  return (
    <Stack>
      <RecoveryCodeList codes={codes} />
      <Group justify="flex-end">
        <Button onClick={onDone}>Ich habe die Codes gesichert</Button>
      </Group>
    </Stack>
  );
}

function RecoveryCodeList({ codes }: { codes: string[] }) {
  return (
    <Stack gap="xs">
      <SimpleGrid cols={2} spacing="xs" data-testid="recovery-codes">
        {codes.map((c) => (
          <Code key={c} fz="md" ta="center">
            {c}
          </Code>
        ))}
      </SimpleGrid>
      <Group justify="flex-end">
        <CopyButton value={codes.join("\n")}>
          {({ copied, copy }) => (
            <Button
              variant="light"
              size="xs"
              leftSection={copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
              onClick={copy}
            >
              {copied ? "Kopiert" : "Alle kopieren"}
            </Button>
          )}
        </CopyButton>
      </Group>
    </Stack>
  );
}

// --- Geraete -------------------------------------------------------------------------------------

function SessionsSection() {
  const queryClient = useQueryClient();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => call(api.GET("/api/v1/auth/sessions")) });
  const end = useMutation({
    mutationFn: (id: string | null) =>
      id
        ? call(api.DELETE("/api/v1/auth/sessions/{session_id}", { params: { path: { session_id: id } } }))
        : call(api.DELETE("/api/v1/auth/sessions")),
    onSuccess: (_r, id) => {
      notifySuccess(id ? "Gerät abgemeldet" : "Alle anderen Geräte abgemeldet");
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (e) => notifyError(e, "Abmelden nicht möglich"),
  });

  if (sessions.isPending) return <Loader size="sm" />;
  if (sessions.isError) return <Alert color="red">{sessions.error.message}</Alert>;
  const others = sessions.data.filter((s) => !s.current).length;

  return (
    <Stack gap="xs">
      <Text size="sm" c="dimmed">
        Unbekanntes Gerät? Abmelden und das Passwort ändern.
      </Text>
      {sessions.data.map((s) => (
        <Group key={s.id} justify="space-between" wrap="nowrap" data-testid="session">
          <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
            {/iphone|ipad|android/i.test(s.device) ? <IconDeviceMobile size={22} /> : <IconDeviceDesktop size={22} />}
            <div style={{ minWidth: 0 }}>
              <Group gap={6}>
                <Text size="sm" fw={500}>
                  {s.device}
                </Text>
                {s.current && (
                  <Badge size="xs" variant="light">
                    dieses Gerät
                  </Badge>
                )}
              </Group>
              <Text size="xs" c="dimmed">
                {[s.ip, s.last_used_at ? `zuletzt ${formatDateTime(s.last_used_at)}` : null]
                  .filter(Boolean)
                  .join(" · ")}
              </Text>
            </div>
          </Group>
          {!s.current && (
            <Tooltip label="Abmelden">
              <ActionIcon
                variant="subtle"
                color="red"
                onClick={() => end.mutate(s.id)}
                aria-label={`${s.device} abmelden`}
              >
                <IconLogout size={18} />
              </ActionIcon>
            </Tooltip>
          )}
        </Group>
      ))}
      {others > 0 && (
        <Group justify="flex-end">
          <Button
            variant="subtle"
            color="red"
            size="xs"
            onClick={() =>
              modals.openConfirmModal({
                title: "Überall sonst abmelden?",
                children: <Text size="sm">Alle anderen Geräte müssen sich danach neu anmelden.</Text>,
                labels: { confirm: "Abmelden", cancel: "Abbrechen" },
                confirmProps: { color: "red" },
                onConfirm: () => end.mutate(null),
              })
            }
          >
            Überall sonst abmelden ({others})
          </Button>
        </Group>
      )}
    </Stack>
  );
}

function NewDeviceHint() {
  const status = useSetupStatus();
  const url = certificatePageUrl(status.data);
  if (!url) return null;
  return (
    <Alert color="blue" variant="light" title="Neues Gerät verbinden">
      Die Verbindung ist mit dem eigenen Zertifikat dieser HomeDMS-Installation verschlüsselt. Damit ein neues Handy
      oder ein neuer PC ihr ohne Warnung vertraut, dort einmal <Anchor href={url}>{url}</Anchor> öffnen und der
      Anleitung folgen.
    </Alert>
  );
}
