import {
  Alert,
  Anchor,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconCheck, IconConfetti } from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router";
import type { DocumentItem } from "../api/client";
import { useAssignCategory, useNeedsReview } from "../api/queries";
import { useCategoryOptions } from "../lib/categories";
import { formatDate, formatPercent, stageLabels } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

/** Dokumente, bei denen die KI unsicher war - hier schnell bestaetigen oder korrigieren. */
export function ReviewPage() {
  const review = useNeedsReview();

  return (
    <Stack>
      <div>
        <Title order={2}>Prüfen</Title>
        <Text c="dimmed" size="sm">
          Bei diesen Dokumenten war sich die KI nicht sicher. Jede Bestätigung verbessert die künftige Einordnung.
        </Text>
      </div>
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
            doc.category_id ? `Vorschlag der KI${suggestion ? ` (${suggestion})` : ""}` : "Keine Kategorie erkannt"
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
