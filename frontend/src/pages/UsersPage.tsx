import {
  ActionIcon,
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  Center,
  Code,
  CopyButton,
  Group,
  Loader,
  Menu,
  Modal,
  PasswordInput,
  SegmentedControl,
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
  IconDots,
  IconKey,
  IconRefresh,
  IconShield,
  IconShieldCheck,
  IconShieldOff,
  IconUser,
  IconUserOff,
  IconUserPlus,
} from "@tabler/icons-react";
import { useState } from "react";
import type { Schemas } from "../api/client";
import { useCreateUser, useResetPassword, useUpdateUser, useUsers } from "../api/queries";
import { useUser } from "../auth/AuthContext";
import { formatDateTime } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";
import { certificatePageUrl, useSetupStatus } from "../lib/connection";
import { generatePassword } from "../lib/password";
import { MailSettingsCard } from "../components/MailSettingsCard";

type Member = Schemas["UserResponse"];

/**
 * Haushaltsmitglieder verwalten (nur Admin): anlegen, Rolle, Passwort zuruecksetzen, deaktivieren.
 * Geloescht wird nie - Dokumente und Termine eines Mitglieds bleiben erhalten.
 */
export function UsersPage() {
  const me = useUser();
  const isAdmin = me.role === "admin";
  const users = useUsers(isAdmin);
  const [creating, setCreating] = useState(false);
  const [resetFor, setResetFor] = useState<Member | null>(null);

  if (!isAdmin) return <Alert color="yellow">Benutzer können nur Administratoren verwalten.</Alert>;

  return (
    <Stack>
      <Group justify="space-between" align="flex-start" wrap="wrap">
        <div>
          <Title order={2}>Benutzer</Title>
          <Text c="dimmed" size="sm" maw={680}>
            Wer HomeDMS nutzen darf. Mitglieder sehen und bearbeiten alle Dokumente des Haushalts (außer aus geschützten
            Kategorien) und ihre eigenen. Admins verwalten zusätzlich Benutzer, Aufbewahrung und den Scan-Ordner.
          </Text>
        </div>
        <Button leftSection={<IconUserPlus size={16} />} onClick={() => setCreating(true)}>
          Mitglied hinzufügen
        </Button>
      </Group>

      {users.isPending ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : users.isError ? (
        <Alert color="red">{users.error.message}</Alert>
      ) : (
        <Stack gap="xs">
          {users.data.map((u) => (
            <MemberCard key={u.id} member={u} isMe={u.id === me.id} onResetPassword={() => setResetFor(u)} />
          ))}
          {users.data.length === 1 && (
            <Text size="sm" c="dimmed">
              Noch niemand außer dir – lege für jedes Familienmitglied ein eigenes Konto an.
            </Text>
          )}
        </Stack>
      )}

      <MailSettingsCard />

      <CreateUserModal opened={creating} onClose={() => setCreating(false)} />
      <ResetPasswordModal member={resetFor} onClose={() => setResetFor(null)} />
    </Stack>
  );
}

function MemberCard({ member, isMe, onResetPassword }: { member: Member; isMe: boolean; onResetPassword(): void }) {
  const update = useUpdateUser();
  const isAdmin = member.role === "admin";

  const change = (body: Schemas["UserUpdate"], success: string) =>
    update.mutate(
      { id: member.id, body },
      { onSuccess: () => notifySuccess(success), onError: (e) => notifyError(e, "Ändern nicht möglich") },
    );

  const confirmDeactivate = () =>
    modals.openConfirmModal({
      title: `${member.display_name} deaktivieren?`,
      children: (
        <Text size="sm">
          {member.display_name} kann sich danach nicht mehr anmelden und wird auf allen Geräten abgemeldet. Dokumente
          und Termine bleiben erhalten; das Konto lässt sich jederzeit wieder aktivieren.
        </Text>
      ),
      labels: { confirm: "Deaktivieren", cancel: "Abbrechen" },
      confirmProps: { color: "red" },
      onConfirm: () => change({ is_active: false }, `${member.display_name} deaktiviert`),
    });

  return (
    <Card withBorder padding="sm" radius="md" data-testid="member" opacity={member.is_active ? 1 : 0.6}>
      <Group justify="space-between" wrap="nowrap">
        <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
          <Avatar radius="xl" color={isAdmin ? "blue" : "gray"}>
            {initials(member.display_name)}
          </Avatar>
          <div style={{ minWidth: 0 }}>
            <Group gap={6} wrap="wrap">
              <Text fw={500} truncate>
                {member.display_name}
                {isMe && " (du)"}
              </Text>
              <Badge size="xs" variant="light" color={isAdmin ? "blue" : "gray"}>
                {isAdmin ? "Admin" : "Mitglied"}
              </Badge>
              {!member.is_active && (
                <Badge size="xs" color="red" variant="light">
                  deaktiviert
                </Badge>
              )}
              {member.two_factor_enabled ? (
                <Badge size="xs" color="green" variant="light" leftSection={<IconShieldCheck size={10} />}>
                  2FA
                </Badge>
              ) : (
                isAdmin && (
                  <Tooltip label="Admin ohne Zwei-Faktor-Anmeldung – unter „Konto & Sicherheit“ einschalten">
                    <Badge size="xs" color="orange" variant="light">
                      ohne 2FA
                    </Badge>
                  </Tooltip>
                )
              )}
            </Group>
            <Text size="sm" c="dimmed" truncate>
              {member.email}
            </Text>
            <Text size="xs" c="dimmed">
              {member.last_login_at
                ? `Zuletzt angemeldet ${formatDateTime(member.last_login_at)}`
                : "Noch nie angemeldet"}
            </Text>
          </div>
        </Group>
        {isMe ? (
          <Tooltip label="Eigenes Profil und Passwort: Benutzermenü oben rechts">
            <IconUser size={18} color="var(--mantine-color-dimmed)" />
          </Tooltip>
        ) : (
          <Menu position="bottom-end" withinPortal>
            <Menu.Target>
              <ActionIcon
                variant="subtle"
                color="gray"
                aria-label={`Aktionen für ${member.display_name}`}
                loading={update.isPending}
              >
                <IconDots size={18} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              {member.is_active && (
                <>
                  <Menu.Item
                    leftSection={<IconShield size={16} />}
                    onClick={() =>
                      change(
                        { role: isAdmin ? "member" : "admin" },
                        isAdmin
                          ? `${member.display_name} ist jetzt Mitglied`
                          : `${member.display_name} ist jetzt Admin`,
                      )
                    }
                  >
                    {isAdmin ? "Zum Mitglied machen" : "Zum Admin machen"}
                  </Menu.Item>
                  <Menu.Item leftSection={<IconKey size={16} />} onClick={onResetPassword}>
                    Passwort zurücksetzen …
                  </Menu.Item>
                  {member.two_factor_enabled && (
                    <Menu.Item
                      leftSection={<IconShieldOff size={16} />}
                      onClick={() =>
                        modals.openConfirmModal({
                          title: `Zwei-Faktor von ${member.display_name} zurücksetzen?`,
                          children: (
                            <Text size="sm">
                              Für den Fall, dass das Handy verloren ist: {member.display_name} meldet sich danach nur
                              mit dem Passwort an und sollte die Zwei-Faktor-Anmeldung neu einrichten.
                            </Text>
                          ),
                          labels: { confirm: "Zurücksetzen", cancel: "Abbrechen" },
                          confirmProps: { color: "red" },
                          onConfirm: () => change({ reset_two_factor: true }, "Zwei-Faktor zurückgesetzt"),
                        })
                      }
                    >
                      Zwei-Faktor zurücksetzen …
                    </Menu.Item>
                  )}
                  <Menu.Divider />
                  <Menu.Item color="red" leftSection={<IconUserOff size={16} />} onClick={confirmDeactivate}>
                    Deaktivieren …
                  </Menu.Item>
                </>
              )}
              {!member.is_active && (
                <Menu.Item
                  leftSection={<IconRefresh size={16} />}
                  onClick={() => change({ is_active: true }, `${member.display_name} ist wieder aktiv`)}
                >
                  Wieder aktivieren
                </Menu.Item>
              )}
            </Menu.Dropdown>
          </Menu>
        )}
      </Group>
    </Card>
  );
}

function CreateUserModal({ opened, onClose }: { opened: boolean; onClose(): void }) {
  return (
    <Modal opened={opened} onClose={onClose} title="Mitglied hinzufügen">
      {opened && <CreateUserForm onClose={onClose} />}
    </Modal>
  );
}

function CreateUserForm({ onClose }: { onClose(): void }) {
  const create = useCreateUser();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState(generatePassword);
  const [role, setRole] = useState<"member" | "admin">("member");
  const [created, setCreated] = useState<Member | null>(null);

  if (created)
    return <Credentials name={created.display_name} email={created.email} password={password} onClose={onClose} />;

  const valid = name.trim() !== "" && /\S+@\S+\.\S+/.test(email.trim()) && password.length >= 8;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate(
          { display_name: name.trim(), email: email.trim(), password, role },
          { onSuccess: setCreated, onError: (err) => notifyError(err, "Anlegen nicht möglich") },
        );
      }}
    >
      <Stack>
        <TextInput
          label="Name"
          placeholder="z. B. Anna"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          data-autofocus
          required
        />
        <TextInput
          label="E-Mail"
          description="Damit meldet sich das Mitglied an"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.currentTarget.value)}
          required
        />
        <PasswordField value={password} onChange={setPassword} label="Startpasswort" />
        <div>
          <Text size="sm" fw={500} mb={4}>
            Rolle
          </Text>
          <SegmentedControl
            fullWidth
            value={role}
            onChange={(v) => setRole(v as "member" | "admin")}
            data={[
              { value: "member", label: "Mitglied" },
              { value: "admin", label: "Admin" },
            ]}
          />
        </div>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Abbrechen
          </Button>
          <Button type="submit" loading={create.isPending} disabled={!valid}>
            Anlegen
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function ResetPasswordModal({ member, onClose }: { member: Member | null; onClose(): void }) {
  return (
    <Modal opened={member !== null} onClose={onClose} title={member ? `Neues Passwort für ${member.display_name}` : ""}>
      {member && <ResetPasswordForm member={member} onClose={onClose} />}
    </Modal>
  );
}

function ResetPasswordForm({ member, onClose }: { member: Member; onClose(): void }) {
  const reset = useResetPassword();
  const [password, setPassword] = useState(generatePassword);
  const [done, setDone] = useState(false);
  if (done)
    return <Credentials name={member.display_name} email={member.email} password={password} onClose={onClose} />;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        reset.mutate(
          { id: member.id, password },
          { onSuccess: () => setDone(true), onError: (err) => notifyError(err, "Zurücksetzen nicht möglich") },
        );
      }}
    >
      <Stack>
        <Text size="sm" c="dimmed">
          {member.display_name} wird auf allen Geräten abgemeldet und meldet sich danach mit dem neuen Passwort an.
        </Text>
        <PasswordField value={password} onChange={setPassword} label="Neues Passwort" />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Abbrechen
          </Button>
          <Button type="submit" loading={reset.isPending} disabled={password.length < 8}>
            Passwort setzen
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function PasswordField({ value, onChange, label }: { value: string; onChange(v: string): void; label: string }) {
  return (
    <Group align="flex-end" gap="xs" wrap="nowrap">
      <PasswordInput
        label={label}
        description="Mindestens 8 Zeichen – das Mitglied kann es später selbst ändern"
        defaultVisible
        value={value}
        onChange={(e) => onChange(e.currentTarget.value)}
        error={value.length > 0 && value.length < 8 ? "Mindestens 8 Zeichen" : undefined}
        style={{ flex: 1 }}
        required
      />
      <Tooltip label="Neues Passwort vorschlagen">
        <ActionIcon
          variant="light"
          size="lg"
          onClick={() => onChange(generatePassword())}
          aria-label="Passwort vorschlagen"
        >
          <IconRefresh size={18} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

/** Zugangsdaten zum Weitergeben - das Passwort wird nur jetzt einmal angezeigt. */
function Credentials({
  name,
  email,
  password,
  onClose,
}: {
  name: string;
  email: string;
  password: string;
  onClose(): void;
}) {
  const certificatePage = certificatePageUrl(useSetupStatus().data);
  const text = [
    `HomeDMS – ${window.location.origin}`,
    `E-Mail: ${email}`,
    `Passwort: ${password}`,
    certificatePage ? `Neues Gerät zuerst einrichten: ${certificatePage}` : null,
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <Stack>
      <Alert color="teal" icon={<IconCheck />}>
        Fertig. Gib {name} diese Zugangsdaten – das Passwort wird nur jetzt angezeigt.
      </Alert>
      <Stack gap={4}>
        <Text size="sm">
          Adresse: <Code>{window.location.origin}</Code>
        </Text>
        <Text size="sm">
          E-Mail: <Code>{email}</Code>
        </Text>
        <Text size="sm">
          Passwort: <Code data-testid="credential-password">{password}</Code>
        </Text>
        {certificatePage && (
          <Text size="sm">
            Neues Gerät zuerst einrichten: <Code>{certificatePage}</Code>
          </Text>
        )}
      </Stack>
      <Group justify="flex-end">
        <CopyButton value={text}>
          {({ copied, copy }) => (
            <Button
              variant="light"
              leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
              onClick={copy}
            >
              {copied ? "Kopiert" : "Zugangsdaten kopieren"}
            </Button>
          )}
        </CopyButton>
        <Button onClick={onClose}>Schließen</Button>
      </Group>
    </Stack>
  );
}

function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join("") || "?"
  );
}
