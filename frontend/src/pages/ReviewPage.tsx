import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconAlertTriangle, IconCheck, IconConfetti, IconRefresh } from "@tabler/icons-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import type { DocumentItem } from "../api/client";
import { useAnalyzeAll, useAssignCategory, useNeedsReview, useUnanalyzed } from "../api/queries";
import { useCategoryOptions } from "../lib/categories";
import { formatDate, formatPercent, stageLabels } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

/**
 * Pruefen: (1) Dokumente, bei denen die KI unsicher war - schnell bestaetigen oder korrigieren;
 * (2) Dokumente, die nicht analysiert werden konnten (KI nicht erreichbar, Auftrag verloren) -
 * mit "Alle analysieren" nachholen.
 */
export function ReviewPage() {
  const review = useNeedsReview();
  const unanalyzed = useUnanalyzed();
  const [params, setParams] = useSearchParams();
  const reviewCount = review.data?.total ?? 0;
  const unanalyzedCount = unanalyzed.data?.total ?? 0;
  // Ohne Auswahl: dort beginnen, wo etwas zu tun ist
  const tab = params.get("ansicht") ?? (reviewCount === 0 && unanalyzedCount > 0 ? "nicht-analysiert" : "kategorie");

  return (
    <Stack>
      <Title order={2}>Prüfen</Title>
      <Tabs value={tab} onChange={(v) => v && setParams({ ansicht: v }, { replace: true })} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab
            value="kategorie"
            rightSection={
              reviewCount ? (
                <Badge size="sm" color="orange" circle={reviewCount < 10}>
                  {reviewCount}
                </Badge>
              ) : null
            }
          >
            Kategorie prüfen
          </Tabs.Tab>
          <Tabs.Tab
            value="nicht-analysiert"
            rightSection={
              unanalyzedCount ? (
                <Badge size="sm" color="red" circle={unanalyzedCount < 10}>
                  {unanalyzedCount}
                </Badge>
              ) : null
            }
          >
            Nicht analysiert
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="kategorie" pt="md">
          <ReviewList review={review} />
        </Tabs.Panel>
        <Tabs.Panel value="nicht-analysiert" pt="md">
          <UnanalyzedList query={unanalyzed} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

function ReviewList({ review }: { review: ReturnType<typeof useNeedsReview> }) {
  return (
    <Stack>
      <Text c="dimmed" size="sm">
        Bei diesen Dokumenten war sich die KI nicht sicher. Jede Bestätigung verbessert die künftige Einordnung.
      </Text>
      {review.isPending ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : review.isError ? (
        <Alert color="red">{review.error.message}</Alert>
      ) : review.data.items.length === 0 ? (
        <Card withBorder padding="xl" radius="md">
          <Stack align="center" gap="xs">
            <ThemeIcon size={48} radius="xl" variant="light" color="green">
              <IconConfetti size={28} />
            </ThemeIcon>
            <Text fw={500}>Alles eingeordnet</Text>
            <Text size="sm" c="dimmed">
              Es gibt nichts zu prüfen.
            </Text>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }}>
          {review.data.items.map((doc) => (
            <ReviewCard key={doc.id} doc={doc} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}

function ReviewCard({ doc }: { doc: DocumentItem }) {
  const options = useCategoryOptions();
  const assign = useAssignCategory();
  const [choice, setChoice] = useState<string | null>(doc.category_id);

  async function confirm() {
    if (!choice) return;
    try {
      await assign.mutateAsync({ documentId: doc.id, categoryId: choice });
      notifySuccess(`„${doc.title}" eingeordnet`);
    } catch (e) {
      notifyError(e, "Einordnen fehlgeschlagen");
    }
  }

  const suggestion = [
    doc.classification_stage ? stageLabels[doc.classification_stage] : null,
    formatPercent(doc.classification_confidence) || null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <Card withBorder radius="md" padding="md">
      <Stack gap="sm">
        <div>
          <Anchor component={Link} to={`/dokumente/${doc.id}`} fw={600} style={{ overflowWrap: "anywhere" }}>
            {doc.title || "Ohne Titel"}
          </Anchor>
          <Text size="xs" c="dimmed">
            {[doc.issuer, formatDate(doc.document_date ?? doc.created_at)].filter(Boolean).join(" · ")}
          </Text>
        </div>
        <Select
          label={
            doc.classification_error
              ? "KI war nicht erreichbar – selbst wählen oder unter „Nicht analysiert“ nachholen"
              : doc.category_id
                ? `Vorschlag der KI${suggestion ? ` (${suggestion})` : ""}`
                : "Keine Kategorie erkannt"
          }
          placeholder="Kategorie wählen"
          data={options}
          value={choice}
          onChange={setChoice}
          searchable
          allowDeselect={false}
        />
        <Group justify="flex-end">
          <Button
            leftSection={<IconCheck size={16} />}
            onClick={() => void confirm()}
            disabled={!choice}
            loading={assign.isPending}
          >
            {choice && choice === doc.category_id ? "Bestätigen" : "Zuordnen"}
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function UnanalyzedList({ query }: { query: ReturnType<typeof useUnanalyzed> }) {
  const analyze = useAnalyzeAll();

  if (query.isPending) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  if (query.isError) return <Alert color="red">{query.error.message}</Alert>;
  const { items, ai_available: aiAvailable } = query.data;

  if (items.length === 0) {
    return (
      <Card withBorder padding="xl" radius="md">
        <Stack align="center" gap="xs">
          <ThemeIcon size={48} radius="xl" variant="light" color="green">
            <IconConfetti size={28} />
          </ThemeIcon>
          <Text fw={500}>Alles analysiert</Text>
          <Text size="sm" c="dimmed">
            Texterkennung, Kategorie und Angaben sind bei allen Dokumenten durchgelaufen.
          </Text>
        </Stack>
      </Card>
    );
  }

  function start() {
    analyze.mutate(undefined, {
      onSuccess: (r) =>
        notifySuccess(
          r.queued
            ? `${r.queued} ${r.queued === 1 ? "Dokument wird" : "Dokumente werden"} analysiert – das kann je nach KI einige Minuten dauern.`
            : "Nichts mehr zu tun.",
        ),
      onError: (e) => notifyError(e, "Analyse konnte nicht gestartet werden"),
    });
  }

  const needsAi = items.some((d) => d.reasons.some((r) => !r.startsWith("Texterkennung")));
  return (
    <Stack>
      <Group justify="space-between" align="flex-start" wrap="wrap">
        <Text c="dimmed" size="sm" maw={640}>
          Bei diesen Dokumenten fehlt ein Teil der Auswertung – meist, weil die KI (Ollama) nicht lief, oder weil die
          Verarbeitung unterbrochen wurde. Nachgeholt wird nur, was fehlt; deine Eingaben bleiben.
        </Text>
        <Button leftSection={<IconRefresh size={16} />} onClick={start} loading={analyze.isPending}>
          Alle analysieren ({items.length})
        </Button>
      </Group>
      {!aiAvailable && needsAi && (
        <Alert color="yellow" icon={<IconAlertTriangle />} title="Die KI antwortet gerade nicht">
          Kategorie, Betreff und Fristen lassen sich erst nachholen, wenn Ollama läuft (unter Windows: am PC anmelden
          bzw. Ollama starten; auf der NAS: Container „ollama“ prüfen). Die Texterkennung klappt auch ohne.
        </Alert>
      )}
      <Stack gap="xs">
        {items.map((doc) => (
          <Card key={doc.id} withBorder padding="sm" radius="md" data-testid="unanalyzed">
            <Group justify="space-between" wrap="nowrap" align="flex-start">
              <div style={{ minWidth: 0 }}>
                <Anchor component={Link} to={`/dokumente/${doc.id}`} fw={600} style={{ overflowWrap: "anywhere" }}>
                  {doc.title || "Ohne Titel"}
                </Anchor>
                <Text size="xs" c="dimmed">
                  hochgeladen {formatDate(doc.created_at)}
                </Text>
              </div>
            </Group>
            <Group gap={6} mt={6}>
              {doc.reasons.map((reason) => (
                <Badge key={reason} variant="light" color="orange" size="sm" tt="none">
                  {reason}
                </Badge>
              ))}
            </Group>
          </Card>
        ))}
      </Stack>
    </Stack>
  );
}
