import {
  Alert,
  Anchor,
  Button,
  Card,
  Center,
  CloseButton,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { useDebouncedValue, useMediaQuery } from "@mantine/hooks";
import { IconCamera, IconFiles, IconSearch, IconUpload } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import type { DocumentItem } from "../api/client";
import { useDocuments, type DocumentFilters } from "../api/queries";
import { SearchSnippet } from "../components/SearchSnippet";
import { DocumentStatusBadge } from "../components/StatusBadge";
import { useOpenUpload } from "../components/upload-context";
import { useCategoryNames, useCategoryOptions } from "../lib/categories";
import { formatAmount, formatDate } from "../lib/format";

const PAGE_SIZE = 25;
const STATUS_OPTIONS = [
  { value: "needs_review", label: "zu prüfen" },
  { value: "auto_assigned", label: "automatisch eingeordnet" },
  { value: "confirmed", label: "bestätigt" },
  { value: "pending", label: "wird verarbeitet" },
];

export function DocumentsPage() {
  const isMobile = useMediaQuery("(max-width: 48em)") ?? false;
  const [params, setParams] = useSearchParams();
  const openUpload = useOpenUpload();
  const categoryOptions = useCategoryOptions();

  // Filter stehen in der Adresszeile -> "Zurueck" aus der Detailansicht behaelt sie
  // Suchfeld: sofort tippen, aber erst nach einer kurzen Pause suchen
  const [searchInput, setSearchInput] = useState(params.get("suche") ?? "");
  const [search] = useDebouncedValue(searchInput.trim(), 300);
  useEffect(() => {
    if ((params.get("suche") ?? "") === search) return;
    const next = new URLSearchParams(params);
    if (search) next.set("suche", search);
    else next.delete("suche");
    next.delete("seite");
    setParams(next, { replace: true });
  }, [search, params, setParams]);

  const filters: DocumentFilters = {
    page: Math.max(1, Number(params.get("seite")) || 1),
    page_size: PAGE_SIZE,
    category_id: params.get("kategorie") ?? undefined,
    status: (params.get("status") as DocumentFilters["status"]) ?? undefined,
    q: params.get("suche") || undefined,
  };
  const documents = useDocuments(filters);

  function setFilter(key: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "seite") next.delete("seite");
    setParams(next, { replace: true });
  }

  const totalPages = documents.data ? Math.max(1, Math.ceil(documents.data.total / PAGE_SIZE)) : 1;
  const hasFilter = Boolean(filters.category_id || filters.status || filters.q);

  return (
    <Stack>
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={2}>Dokumente</Title>
          {documents.data && (
            <Text c="dimmed" size="sm">
              {documents.data.total} {documents.data.total === 1 ? "Dokument" : "Dokumente"}
            </Text>
          )}
        </div>
        <Group gap="xs" grow={isMobile} w={isMobile ? "100%" : undefined} wrap={isMobile ? "wrap" : "nowrap"}>
          <TextInput
            placeholder="Suchen in Titel, Absender, Text …"
            leftSection={<IconSearch size={16} />}
            value={searchInput}
            onChange={(e) => setSearchInput(e.currentTarget.value)}
            rightSection={
              searchInput ? (
                <CloseButton size="sm" onClick={() => setSearchInput("")} aria-label="Suche löschen" />
              ) : undefined
            }
            aria-label="Suche"
            type="search"
            w={isMobile ? "100%" : 280}
            style={isMobile ? { flexBasis: "100%" } : undefined}
          />
          <Select
            placeholder="Alle Kategorien"
            data={categoryOptions}
            value={filters.category_id ?? null}
            onChange={(v) => setFilter("kategorie", v)}
            clearable
            searchable
            aria-label="Kategorie"
            w={isMobile ? undefined : 220}
          />
          <Select
            placeholder="Jeder Status"
            data={STATUS_OPTIONS}
            value={filters.status ?? null}
            onChange={(v) => setFilter("status", v)}
            clearable
            aria-label="Status"
            w={isMobile ? undefined : 200}
          />
        </Group>
      </Group>

      {documents.isPending ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : documents.isError ? (
        <Alert color="red" title="Dokumente konnten nicht geladen werden">
          {documents.error.message}
        </Alert>
      ) : documents.data.items.length === 0 ? (
        hasFilter ? (
          <Text c="dimmed" ta="center" py="xl">
            {filters.q ? `Nichts gefunden für „${filters.q}“.` : "Keine Dokumente für diesen Filter."}
          </Text>
        ) : (
          <EmptyState onUpload={() => openUpload("files")} onCamera={() => openUpload("camera")} />
        )
      ) : isMobile ? (
        <DocumentCards items={documents.data.items} />
      ) : (
        <DocumentTable items={documents.data.items} />
      )}

      {totalPages > 1 && (
        <Center>
          <Pagination
            total={totalPages}
            value={filters.page}
            onChange={(p) => setFilter("seite", String(p))}
            size={isMobile ? "sm" : "md"}
          />
        </Center>
      )}
    </Stack>
  );
}

function DocumentTable({ items }: { items: DocumentItem[] }) {
  const navigate = useNavigate();
  const categoryName = useCategoryNames();
  return (
    <Table.ScrollContainer minWidth={760}>
      <Table highlightOnHover verticalSpacing="sm">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Titel</Table.Th>
            <Table.Th>Kategorie</Table.Th>
            <Table.Th>Datum</Table.Th>
            <Table.Th>Aussteller</Table.Th>
            <Table.Th ta="right">Betrag</Table.Th>
            <Table.Th>Status</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {items.map((doc) => (
            <Table.Tr key={doc.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/dokumente/${doc.id}`)}>
              <Table.Td maw={320}>
                <Anchor
                  component={Link}
                  to={`/dokumente/${doc.id}`}
                  fw={500}
                  c="var(--mantine-color-text)"
                  underline="hover"
                  truncate
                  display="block"
                  onClick={(e) => e.stopPropagation()}
                >
                  {doc.title || "Ohne Titel"}
                </Anchor>
                {doc.search_snippet ? (
                  <SearchSnippet segments={doc.search_snippet} />
                ) : (
                  <Text size="xs" c="dimmed">
                    hochgeladen {formatDate(doc.created_at)}
                  </Text>
                )}
              </Table.Td>
              <Table.Td>
                <Text size="sm" c={doc.category_id ? undefined : "dimmed"}>
                  {categoryName(doc.category_id)}
                </Text>
              </Table.Td>
              <Table.Td>{formatDate(doc.document_date)}</Table.Td>
              <Table.Td maw={200}>
                <Text size="sm" truncate>
                  {doc.issuer ?? "–"}
                </Text>
              </Table.Td>
              <Table.Td ta="right" style={{ whiteSpace: "nowrap" }}>
                {formatAmount(doc.amount)}
              </Table.Td>
              <Table.Td>
                <DocumentStatusBadge doc={doc} />
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

function DocumentCards({ items }: { items: DocumentItem[] }) {
  const categoryName = useCategoryNames();
  return (
    <Stack gap="xs">
      {items.map((doc) => (
        <UnstyledButton key={doc.id} component={Link} to={`/dokumente/${doc.id}`}>
          <Card withBorder padding="sm" radius="md">
            <Text fw={500} lineClamp={2} style={{ overflowWrap: "anywhere" }}>
              {doc.title || "Ohne Titel"}
            </Text>
            <Text size="sm" c="dimmed" mt={2}>
              {[categoryName(doc.category_id), doc.issuer].filter(Boolean).join(" · ")}
            </Text>
            <SearchSnippet segments={doc.search_snippet} />
            <Group justify="space-between" mt={6} wrap="nowrap">
              <Group gap="xs" wrap="nowrap">
                <Text size="sm">{formatDate(doc.document_date ?? doc.created_at)}</Text>
                <DocumentStatusBadge doc={doc} />
              </Group>
              {doc.amount !== null && (
                <Text size="sm" fw={500} style={{ whiteSpace: "nowrap" }}>
                  {formatAmount(doc.amount)}
                </Text>
              )}
            </Group>
          </Card>
        </UnstyledButton>
      ))}
    </Stack>
  );
}

function EmptyState({ onUpload, onCamera }: { onUpload(): void; onCamera(): void }) {
  return (
    <Card withBorder padding="xl" radius="md">
      <Stack align="center" gap="sm">
        <IconFiles size={48} color="var(--mantine-color-dimmed)" />
        <Title order={3}>Noch keine Dokumente</Title>
        <Text c="dimmed" ta="center" maw={420}>
          Laden Sie ein PDF oder einen Scan hoch oder fotografieren Sie einen Brief mit dem Handy. Texterkennung und
          Einordnung laufen danach automatisch.
        </Text>
        <Group>
          <Button leftSection={<IconUpload size={16} />} onClick={onUpload}>
            Hochladen
          </Button>
          <Button variant="light" leftSection={<IconCamera size={16} />} onClick={onCamera}>
            Foto aufnehmen
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
