import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Center,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import {
  IconAlertTriangle,
  IconBell,
  IconBrain,
  IconCircleCheck,
  IconCircleMinus,
  IconCircleX,
  IconCloudDownload,
  IconCpu,
  IconDatabase,
  IconDownload,
  IconFolder,
  IconLanguage,
  IconLock,
  IconRefresh,
  IconScan,
  IconSearch,
  IconServer,
  IconTrash,
} from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { Schemas } from "../api/client";
import {
  useBackups,
  useCheckUpdates,
  useCreateBackup,
  useDeleteBackup,
  useDiagnostics,
  useInstallUpdate,
  useSystemAction,
  useUpdaterStatus,
  UPDATE_ACTIVE,
} from "../api/queries";
import { useUser } from "../auth/AuthContext";
import { downloadBackup } from "../lib/download";
import { formatBytes, formatDateTime, tk } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

type Component = Schemas["DiagnosticComponent"];
type Status = Component["status"];

const STATUS: Record<Status, { label: string; color: string; icon: ReactNode }> = {
  ok: { label: tk("OK"), color: "green", icon: <IconCircleCheck size={16} /> },
  warning: { label: tk("Warnung"), color: "yellow", icon: <IconAlertTriangle size={16} /> },
  error: { label: tk("Fehler"), color: "red", icon: <IconCircleX size={16} /> },
  disabled: { label: tk("aus"), color: "gray", icon: <IconCircleMinus size={16} /> },
};

const ICONS: Record<string, ReactNode> = {
  app: <IconServer size={20} />,
  database: <IconDatabase size={20} />,
  worker: <IconCpu size={20} />,
  ai: <IconBrain size={20} />,
  search: <IconSearch size={20} />,
  ocr: <IconScan size={20} />,
  storage: <IconFolder size={20} />,
  tls: <IconLock size={20} />,
  notifications: <IconBell size={20} />,
  ocr_languages: <IconLanguage size={20} />,
};

/**
 * Diagnose (nur Admins): Zustand aller Bausteine - Datenbank, Worker, KI, Suche, Texterkennung,
 * Speicher - mit Hinweisen und einfachen Reparatur-Aktionen. Aktualisiert sich alle 10 Sekunden.
 */
export function DiagnosePage() {
  const user = useUser();
  const { t } = useTranslation();
  const diagnostics = useDiagnostics();

  if (user.role !== "admin") return <Alert color="yellow">{t("Die Diagnose ist nur für Administratoren.")}</Alert>;

  return (
    <Stack>
      <Group justify="space-between" align="flex-start" wrap="wrap">
        <div>
          <Title order={2}>{t("Diagnose")}</Title>
          <Text c="dimmed" size="sm">
            {t("Zustand aller Bausteine von Famulus DMS")}
            {diagnostics.data && ` · ${t("geprüft {{date}}", { date: formatDateTime(diagnostics.data.checked_at) })}`}
          </Text>
          {diagnostics.data && <Updates version={diagnostics.data.version} />}
        </div>
        <Button
          variant="light"
          leftSection={<IconRefresh size={16} />}
          loading={diagnostics.isFetching}
          onClick={() => void diagnostics.refetch()}
        >
          {t("Jetzt prüfen")}
        </Button>
      </Group>

      {diagnostics.isPending ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : diagnostics.isError ? (
        <Alert color="red" title={t("Diagnose nicht möglich")}>
          {diagnostics.error.message}
        </Alert>
      ) : (
        <>
          <Summary components={diagnostics.data.components} />
          <SimpleGrid cols={{ base: 1, sm: 2, xl: 3 }}>
            {diagnostics.data.components.map((c) => (
              <ComponentCard key={c.key} component={c} />
            ))}
          </SimpleGrid>
          <Backups />
          <Failures items={diagnostics.data.recent_failures} />
        </>
      )}
    </Stack>
  );
}

function Summary({ components }: { components: Component[] }) {
  const { t } = useTranslation();
  const problems = components.filter((c) => c.status === "error" || c.status === "warning");
  if (problems.length === 0) {
    return (
      <Alert color="green" icon={<IconCircleCheck />} title={t("Alles in Ordnung")}>
        {t("Alle Bausteine laufen.")}
      </Alert>
    );
  }
  const hasError = problems.some((c) => c.status === "error");
  return (
    <Alert
      color={hasError ? "red" : "yellow"}
      icon={hasError ? <IconCircleX /> : <IconAlertTriangle />}
      title={t("{{count}} Bausteine brauchen Aufmerksamkeit", { count: problems.length })}
    >
      {problems.map((c) => `${c.name}: ${c.summary}`).join(" · ")}
    </Alert>
  );
}

function ComponentCard({ component }: { component: Component }) {
  const { t } = useTranslation();
  const action = useSystemAction();
  const state = STATUS[component.status];

  function run(a: Schemas["DiagnosticAction"]) {
    const go = () =>
      action.mutate(a.id, {
        onSuccess: (r) => notifySuccess(r.message),
        onError: (e) => notifyError(e, t("{{action}} nicht möglich", { action: a.label })),
      });
    if (!a.confirm) return go();
    modals.openConfirmModal({
      title: `${a.label}?`,
      children: <Text size="sm">{a.confirm}</Text>,
      labels: { confirm: a.label, cancel: t("Abbrechen") },
      onConfirm: go,
    });
  }

  return (
    <Card withBorder radius="md" padding="md" data-testid={`component-${component.key}`}>
      <Stack gap="sm" h="100%">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Group gap="sm" wrap="nowrap">
            <ThemeIcon variant="light" color={state.color} size="lg" radius="md">
              {ICONS[component.key] ?? <IconServer size={20} />}
            </ThemeIcon>
            <div>
              <Text fw={600}>{component.name}</Text>
              <Text size="sm" c="dimmed">
                {component.summary}
              </Text>
            </div>
          </Group>
          <Badge color={state.color} variant="light" leftSection={state.icon} style={{ flexShrink: 0 }}>
            {t(state.label)}
          </Badge>
        </Group>

        {component.details.length > 0 && (
          <Table withRowBorders={false} verticalSpacing={2} horizontalSpacing={0} fz="sm">
            <Table.Tbody>
              {component.details.map((d) => (
                <Table.Tr key={d.label}>
                  <Table.Td c="dimmed" w="45%" style={{ verticalAlign: "top" }}>
                    {d.label}
                  </Table.Td>
                  <Table.Td style={{ overflowWrap: "anywhere" }}>{d.value}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}

        {component.hint && (
          <Text size="sm" c={component.status === "error" ? "red" : "dimmed"}>
            {component.hint}
          </Text>
        )}

        {component.actions.length > 0 && (
          <Group gap="xs" mt="auto">
            {component.actions.map((a) => (
              <Button
                key={a.id}
                size="xs"
                variant="light"
                loading={action.isPending && action.variables === a.id}
                onClick={() => run(a)}
              >
                {a.label}
              </Button>
            ))}
          </Group>
        )}
      </Stack>
    </Card>
  );
}

/**
 * Installierte Version und "Auf Updates pruefen" (nur auf Knopfdruck; der Server fragt dann GitHub).
 * Aktualisiert wird nicht von hier aus: das Ergebnis nennt den Weg dorthin.
 */
const UPDATE_STEP: Record<string, string> = {
  requested: tk("Update angefordert – der Update-Helfer holt es gleich ab …"),
  checking: tk("Update wird vorbereitet …"),
  pulling: tk("Neue Version wird heruntergeladen …"),
  restarting: tk("Famulus DMS wird neu gestartet – die Seite ist kurz nicht erreichbar …"),
  health: tk("Warten, bis die neue Version bereit ist …"),
};

function Updates({ version }: { version: string }) {
  const { t } = useTranslation();
  const check = useCheckUpdates();
  const result = check.data;
  const updater = useUpdaterStatus();
  const install = useInstallUpdate();
  const agent = updater.data;
  const busy = !!agent?.state && UPDATE_ACTIVE.includes(agent.state);

  function confirmInstall(latest: string) {
    modals.openConfirmModal({
      title: t("Auf Version {{version}} aktualisieren?", { version: latest }),
      children: (
        <Text size="sm">
          {t("Vorher wird die Datenbank gesichert. Während des Neustarts ist Famulus DMS für etwa eine Minute nicht erreichbar.")}
        </Text>
      ),
      labels: { confirm: t("Jetzt aktualisieren"), cancel: t("Abbrechen") },
      onConfirm: () => install.mutate(latest, { onError: (e) => notifyError(e, t("Aktualisierung nicht möglich")) }),
    });
  }

  return (
    <Stack gap={6} mt={6} data-testid="updates">
      <Group gap="xs">
        <Text size="sm">{t("Version {{version}}", { version })}</Text>
        <Button
          size="compact-xs"
          variant="light"
          leftSection={<IconCloudDownload size={14} />}
          loading={check.isPending}
          onClick={() => check.mutate(undefined, { onError: (e) => notifyError(e, t("Update-Prüfung nicht möglich")) })}
        >
          {t("Auf Updates prüfen")}
        </Button>
      </Group>
      {result &&
        (result.available ? (
          <Alert color="blue" icon={<IconCloudDownload />} title={t("Version {{latest}} ist verfügbar", { latest: result.latest })}>
            <Stack gap={4}>
              <Text size="sm">
                {t("Installiert ist {{current}}. Sichern Sie vor dem Aktualisieren die Datenbank (Abschnitt „Datenbanksicherung“ unten).", {
                  current: result.current,
                })}
              </Text>
              {agent?.available ? (
                <Group>
                  <Button
                    size="xs"
                    leftSection={<IconCloudDownload size={14} />}
                    loading={install.isPending}
                    disabled={busy}
                    onClick={() => confirmInstall(result.latest)}
                  >
                    {t("Jetzt aktualisieren")}
                  </Button>
                </Group>
              ) : (
                <Text size="sm">
                  {t("Bei Docker: In der Compose-Datei das Image auf {{image}} setzen und das Projekt neu erstellen.", {
                    image: `ghcr.io/sschneidt/famulus-dms:${result.latest}`,
                  })}
                </Text>
              )}
              <Group gap="md">
                {result.url && (
                  <Anchor size="sm" href={result.url} target="_blank" rel="noreferrer">
                    {t("Änderungen ansehen")}
                  </Anchor>
                )}
                <Anchor
                  size="sm"
                  href="https://github.com/sschneidt/famulus-dms/blob/main/docs/Updates.md"
                  target="_blank"
                  rel="noreferrer"
                >
                  {t("Anleitung zum Aktualisieren")}
                </Anchor>
              </Group>
            </Stack>
          </Alert>
        ) : (
          <Text size="sm" c="green">
            {t("Sie nutzen die neueste Version ({{version}}).", { version: result.current })}
          </Text>
        ))}
      {agent?.state && busy && (
        <Alert color="blue" icon={<Loader size={16} />} data-testid="update-progress">
          <Text size="sm">{t(UPDATE_STEP[agent.state] ?? "")}</Text>
        </Alert>
      )}
      {agent?.state === "done" && agent.version !== version && (
        <Alert color="green" icon={<IconCircleCheck />} title={t("Aktualisiert auf Version {{version}}", { version: agent.version })}>
          <Stack gap={6} align="flex-start">
            <Text size="sm">{t("Laden Sie die Seite neu, um die neue Version zu verwenden.")}</Text>
            <Button size="xs" onClick={() => window.location.reload()}>
              {t("Seite neu laden")}
            </Button>
          </Stack>
        </Alert>
      )}
      {(agent?.state === "failed" || agent?.state === "rolled_back") && (
        <Alert color="red" icon={<IconAlertTriangle />} title={t("Das Update ist fehlgeschlagen")} data-testid="update-failed">
          <Stack gap={4}>
            <Text size="sm">
              {agent.state === "rolled_back"
                ? t("Die neue Version ist nicht gestartet, die alte läuft wieder. Die Datenbanksicherung von vor dem Update finden Sie unter „Datenbanksicherung“.")
                : agent.detail === "not_picked_up"
                  ? t("Der Update-Helfer hat die Anforderung nicht abgeholt. Läuft er noch?")
                  : t("Es wurde nichts verändert.")}
            </Text>
            {agent.detail && agent.detail !== "not_picked_up" && (
              <Text size="xs" c="dimmed">
                {t("Meldung des Update-Helfers: {{detail}}", { detail: agent.detail })}
              </Text>
            )}
          </Stack>
        </Alert>
      )}
    </Stack>
  );
}

/** Datenbanksicherung aus der Anwendung: anlegen, herunterladen, loeschen (Admins). */
function Backups() {
  const { t } = useTranslation();
  const backups = useBackups();
  const create = useCreateBackup();
  const remove = useDeleteBackup();

  function confirmDelete(name: string) {
    modals.openConfirmModal({
      title: t("Sicherung löschen?"),
      children: <Text size="sm">{t("Die Sicherung {{name}} wird endgültig gelöscht.", { name })}</Text>,
      labels: { confirm: t("Löschen"), cancel: t("Abbrechen") },
      confirmProps: { color: "red" },
      onConfirm: () => remove.mutate(name, { onError: (e) => notifyError(e, t("Löschen nicht möglich")) }),
    });
  }

  return (
    <Stack gap="xs" data-testid="backups">
      <Group justify="space-between" align="flex-start" wrap="wrap">
        <div>
          <Title order={4}>{t("Datenbanksicherung")}</Title>
          <Text size="sm" c="dimmed">
            {t(
              "Sichert die Datenbank (Personen, Angaben zu den Dokumenten, Fristen, Einstellungen). Die Dokument-Dateien selbst liegen im Dokumente-Ordner und werden als Ordner gesichert.",
            )}
          </Text>
        </div>
        <Button
          leftSection={<IconDatabase size={16} />}
          loading={create.isPending}
          disabled={backups.data?.available === false}
          onClick={() =>
            create.mutate(undefined, {
              onSuccess: () => notifySuccess(t("Sicherung angelegt.")),
              onError: (e) => notifyError(e, t("Sicherung nicht möglich")),
            })
          }
        >
          {t("Jetzt sichern")}
        </Button>
      </Group>

      {backups.isPending ? (
        <Loader size="sm" />
      ) : backups.isError ? (
        <Alert color="red">{backups.error.message}</Alert>
      ) : (
        <>
          {!backups.data.available && (
            <Alert color="yellow" icon={<IconAlertTriangle />}>
              {t(
                "Auf diesem Server fehlt das Programm pg_dump. Eine Sicherung geht hier nur mit den Update-Skripten (siehe Anleitung).",
              )}
            </Alert>
          )}
          <Text size="sm" c="dimmed">
            {t("Ordner: {{folder}} · Aufbewahrt werden die neuesten {{keep}} Sicherungen.", {
              folder: backups.data.folder,
              keep: backups.data.keep,
            })}
          </Text>
          {backups.data.items.length === 0 ? (
            <Text size="sm">{t("Noch keine Sicherung vorhanden.")}</Text>
          ) : (
            <Card withBorder padding={0} radius="md">
              <Table striped fz="sm">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t("Datei")}</Table.Th>
                    <Table.Th>{t("Erstellt")}</Table.Th>
                    <Table.Th>{t("Größe")}</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {backups.data.items.map((b) => (
                    <Table.Tr key={b.name}>
                      <Table.Td style={{ overflowWrap: "anywhere" }}>{b.name}</Table.Td>
                      <Table.Td style={{ whiteSpace: "nowrap" }}>{formatDateTime(b.created)}</Table.Td>
                      <Table.Td style={{ whiteSpace: "nowrap" }}>{formatBytes(b.size)}</Table.Td>
                      <Table.Td>
                        <Group gap="xs" wrap="nowrap" justify="flex-end">
                          <Button
                            size="compact-xs"
                            variant="light"
                            leftSection={<IconDownload size={14} />}
                            aria-label={`${t("Herunterladen")} ${b.name}`}
                            onClick={() => downloadBackup(b.name).catch((e) => notifyError(e, t("Download fehlgeschlagen")))}
                          >
                            {t("Herunterladen")}
                          </Button>
                          <Button
                            size="compact-xs"
                            variant="subtle"
                            color="red"
                            leftSection={<IconTrash size={14} />}
                            aria-label={`${t("Löschen")} ${b.name}`}
                            onClick={() => confirmDelete(b.name)}
                          >
                            {t("Löschen")}
                          </Button>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Card>
          )}
        </>
      )}
    </Stack>
  );
}

function Failures({ items }: { items: Schemas["FailedJob"][] }) {
  const { t } = useTranslation();
  if (items.length === 0) return null;
  return (
    <Stack gap="xs">
      <Title order={4}>{t("Fehlgeschlagene Aufträge (7 Tage)")}</Title>
      <Text size="sm" c="dimmed">
        <Trans
          i18nKey="Betroffene Dokumente lassen sich unter <anchor>Prüfen > Nicht analysiert</anchor> neu analysieren."
          components={{ anchor: <Anchor component={Link} to="/pruefen?ansicht=nicht-analysiert" /> }}
        />
      </Text>
      <Card withBorder padding={0} radius="md">
        <Table striped fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("Zeit")}</Table.Th>
              <Table.Th>{t("Auftrag")}</Table.Th>
              <Table.Th>{t("Dokument")}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((f) => (
              <Table.Tr key={f.job_id}>
                <Table.Td style={{ whiteSpace: "nowrap" }}>{formatDateTime(f.at)}</Table.Td>
                <Table.Td>{f.task}</Table.Td>
                <Table.Td>
                  {f.document_id ? (
                    <Anchor component={Link} to={`/dokumente/${f.document_id}`}>
                      {f.document_title || t("Dokument")}
                    </Anchor>
                  ) : (
                    "–"
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  );
}
