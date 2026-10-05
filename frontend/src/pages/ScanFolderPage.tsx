import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Center,
  Code,
  Group,
  Loader,
  Stack,
  Switch,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { IconAlertTriangle, IconFolderSearch, IconRefresh } from "@tabler/icons-react";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { Schemas } from "../api/client";
import {
  useCreateImportSource,
  useImportSources,
  useScanFolderInfo,
  useScanNow,
  useUpdateImportSource,
} from "../api/queries";
import { useUser } from "../auth/AuthContext";
import { formatDateTime, tk } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

type Source = Schemas["ImportSourceResponse"];
type Entry = Schemas["ImportLogEntry"];

const STATUS: Record<string, { label: string; color: string }> = {
  importiert: { label: tk("importiert"), color: "green" },
  duplikat: { label: tk("schon vorhanden"), color: "gray" },
  fehler: { label: tk("Fehler"), color: "red" },
};

/** Scan-Ordner (nur Admins): Status, letzte Importe, "Jetzt prüfen". */
export function ScanFolderPage() {
  const user = useUser();
  const { t } = useTranslation();
  const isAdmin = user.role === "admin";
  const sources = useImportSources(isAdmin);
  const create = useCreateImportSource();

  if (!isAdmin) return <Alert color="yellow">{t("Den Scan-Ordner können nur Administratoren verwalten.")}</Alert>;

  return (
    <Stack>
      <div>
        <Title order={2}>{t("Scan-Ordner")}</Title>
        <Text c="dimmed" size="sm" maw={720}>
          <Trans
            i18nKey="Was der Scanner (oder Sie) in den Scan-Ordner auf dem NAS legt, holt HomeDMS jede Minute automatisch ab: PDF, JPG, PNG, TIFF, HEIC und E-Mails (.eml). Die Dokumente gehören dem ganzen Haushalt. Das Original wandert danach nach <code>_importiert</code>, Unbrauchbares nach <code>_fehler</code>."
            components={{ code: <Code /> }}
          />
        </Text>
      </div>
      <LocationCard />
      {sources.isPending ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : sources.isError ? (
        <Alert color="red">{sources.error.message}</Alert>
      ) : sources.data.length === 0 ? (
        <Card withBorder padding="xl" radius="md">
          <Stack align="center" gap="sm">
            <IconFolderSearch size={40} color="var(--mantine-color-dimmed)" />
            <Text c="dimmed" ta="center" maw={460}>
              {t(
                "Noch nicht eingerichtet. Bei einem einzelnen Haushalt geschieht das beim ersten Durchlauf automatisch – oder jetzt per Knopfdruck.",
              )}
            </Text>
            <Button
              loading={create.isPending}
              onClick={() =>
                create.mutate("", {
                  onSuccess: () => notifySuccess(t("Scan-Ordner eingerichtet")),
                  onError: (e) => notifyError(e),
                })
              }
            >
              {t("Scan-Ordner einrichten")}
            </Button>
          </Stack>
        </Card>
      ) : (
        sources.data.map((s) => <SourceCard key={s.id} source={s} />)
      )}
    </Stack>
  );
}

/** Wo der Scan-Ordner liegt - festgelegt beim Start, nicht hier (der Container sieht nur eingebundene Ordner). */
function LocationCard() {
  const info = useScanFolderInfo(true);
  const { t } = useTranslation();
  if (!info.data) return null;
  const { location, docker, setting } = info.data;
  const relative = location.startsWith(".");
  return (
    <Card withBorder padding="md" radius="md">
      <Stack gap={6}>
        <Group gap="xs" wrap="wrap">
          <Text fw={500}>{docker ? t("Ordner auf dem NAS/PC:") : t("Ordner auf diesem Rechner:")}</Text>
          <Code data-testid="scan-location">{location}</Code>
        </Group>
        <Text size="sm" c="dimmed">
          {docker ? (
            <>
              <Trans
                i18nKey="Ändern: in der Datei <code>.env</code> neben <code>docker-compose.yml</code> die Zeile <code>{{setting}}=…</code> anpassen (z. B. <code>{{setting}}=/volume1/scan</code>) und danach <code>docker compose up -d</code> ausführen."
                values={{ setting }}
                components={{ code: <Code /> }}
              />
              {relative && ` ${t("Ein Pfad mit ./ beginnt im HomeDMS-Ordner (dort, wo docker-compose.yml liegt).")}`}
            </>
          ) : (
            <>
              <Trans
                i18nKey="Ändern: Einstellung <code>{{setting}}</code> (Umgebungsvariable bzw. <code>.env</code>) anpassen und HomeDMS neu starten."
                values={{ setting }}
                components={{ code: <Code /> }}
              />
            </>
          )}
        </Text>
      </Stack>
    </Card>
  );
}

function SourceCard({ source }: { source: Source }) {
  const { t } = useTranslation();
  const update = useUpdateImportSource();
  const scanNow = useScanNow();
  const isMobile = useMediaQuery("(max-width: 48em)") ?? false;

  return (
    <Stack>
      <Card withBorder padding="md" radius="md">
        <Stack gap="sm">
          <Group justify="space-between" wrap="wrap">
            <Group gap="xs">
              <Text fw={500}>{t("Ordner:")}</Text>
              <Code>{source.path ? `scan/${source.path}` : t("scan/ (ganzer Scan-Ordner)")}</Code>
            </Group>
            <Switch
              label={t("Aktiv")}
              checked={source.is_active}
              onChange={(e) =>
                update.mutate(
                  { id: source.id, body: { is_active: e.currentTarget.checked } },
                  { onError: (err) => notifyError(err) },
                )
              }
            />
          </Group>
          <Group gap="lg">
            <Text size="sm" c="dimmed">
              {t("Zuletzt geprüft: {{date}}", {
                date: source.last_scanned_at ? formatDateTime(source.last_scanned_at) : t("noch nie"),
              })}
            </Text>
            {source.waiting > 0 && (
              <Text size="sm" c="dimmed">
                {t("{{count}} Dateien warten (werden evtl. noch geschrieben)", { count: source.waiting })}
              </Text>
            )}
          </Group>
          {source.error && (
            <Alert color="red" icon={<IconAlertTriangle />} p="xs">
              {source.error}
            </Alert>
          )}
          <Group>
            <Button
              variant="light"
              leftSection={<IconRefresh size={16} />}
              loading={scanNow.isPending}
              disabled={!source.is_active}
              onClick={() =>
                scanNow.mutate(source.id, {
                  onSuccess: () => notifySuccess(t("Scan-Ordner wird geprüft")),
                  onError: (e) => notifyError(e),
                })
              }
            >
              {t("Jetzt prüfen")}
            </Button>
          </Group>
        </Stack>
      </Card>

      <Title order={4}>{t("Letzte Importe")}</Title>
      {source.recent.length === 0 ? (
        <Text c="dimmed" size="sm">
          {t("Noch nichts importiert.")}
        </Text>
      ) : isMobile ? (
        <Stack gap="xs">
          {source.recent.map((e, i) => (
            <Card key={i} withBorder padding="sm" radius="md">
              <Group justify="space-between" wrap="nowrap">
                <EntryFile entry={e} />
                <EntryBadge entry={e} />
              </Group>
              <Text size="xs" c="dimmed">
                {formatDateTime(e.at)} {e.message && `· ${e.message}`}
              </Text>
            </Card>
          ))}
        </Stack>
      ) : (
        <Table verticalSpacing="xs" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("Zeit")}</Table.Th>
              <Table.Th>{t("Datei")}</Table.Th>
              <Table.Th>{t("Ergebnis")}</Table.Th>
              <Table.Th>{t("Hinweis")}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {source.recent.map((e, i) => (
              <Table.Tr key={i}>
                <Table.Td style={{ whiteSpace: "nowrap" }}>{formatDateTime(e.at)}</Table.Td>
                <Table.Td>
                  <EntryFile entry={e} />
                </Table.Td>
                <Table.Td>
                  <EntryBadge entry={e} />
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {e.message}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}

function EntryFile({ entry }: { entry: Entry }) {
  return entry.document_id ? (
    <Anchor component={Link} to={`/dokumente/${entry.document_id}`} size="sm" style={{ overflowWrap: "anywhere" }}>
      {entry.file}
    </Anchor>
  ) : (
    <Text size="sm" style={{ overflowWrap: "anywhere" }}>
      {entry.file}
    </Text>
  );
}

function EntryBadge({ entry }: { entry: Entry }) {
  const { t } = useTranslation();
  const info = STATUS[entry.status] ?? { label: entry.status, color: "gray" };
  return (
    <Badge color={info.color} variant="light" style={{ flexShrink: 0 }}>
      {t(info.label)}
    </Badge>
  );
}
