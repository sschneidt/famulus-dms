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
  IconCpu,
  IconDatabase,
  IconFolder,
  IconLanguage,
  IconLock,
  IconRefresh,
  IconScan,
  IconSearch,
  IconServer,
} from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { Schemas } from "../api/client";
import { useDiagnostics, useSystemAction } from "../api/queries";
import { useUser } from "../auth/AuthContext";
import { formatDateTime, tk } from "../lib/format";
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
