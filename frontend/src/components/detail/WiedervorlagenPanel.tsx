import { Button, Group, Loader, Paper, Stack, Text, Title } from "@mantine/core";
import { IconPlus } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { DocumentDetail, Wiedervorlage } from "../../api/client";
import { useDocumentWiedervorlagen } from "../../api/queries";
import { isProcessing } from "../../lib/format";
import { WiedervorlageCard } from "../WiedervorlageCard";
import { WiedervorlageForm } from "../WiedervorlageForm";

const ORDER: Record<string, number> = { vorgeschlagen: 0, offen: 1, erledigt: 2, verworfen: 3 };

export function WiedervorlagenPanel({ doc, readOnly = false }: { doc: DocumentDetail; readOnly?: boolean }) {
  const { t } = useTranslation();
  const list = useDocumentWiedervorlagen(doc.id, isProcessing(doc));
  const [editing, setEditing] = useState<{ open: boolean; wv: Wiedervorlage | null }>({ open: false, wv: null });
  const [showDone, setShowDone] = useState(false);

  const items = [...(list.data ?? [])].sort(
    (a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9) || a.due_date.localeCompare(b.due_date),
  );
  const active = items.filter((w) => w.status === "vorgeschlagen" || w.status === "offen");
  const done = items.filter((w) => w.status === "erledigt" || w.status === "verworfen");

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={4}>{t("Termine & Fristen")}</Title>
          {!readOnly && (
            <Button
              size="xs"
              variant="light"
              leftSection={<IconPlus size={14} />}
              onClick={() => setEditing({ open: true, wv: null })}
            >
              {t("Termin")}
            </Button>
          )}
        </Group>
        {list.isPending ? (
          <Loader size="sm" />
        ) : active.length === 0 ? (
          <Text size="sm" c="dimmed">
            {doc.extraction_status === "pending" ? t("Fristen werden gesucht …") : t("Keine offenen Termine.")}
          </Text>
        ) : (
          active.map((wv) => (
            <WiedervorlageCard
              key={wv.id}
              wv={wv}
              onEdit={readOnly ? undefined : (w) => setEditing({ open: true, wv: w })}
            />
          ))
        )}
        {done.length > 0 && (
          <>
            <Button
              variant="subtle"
              size="xs"
              color="gray"
              onClick={() => setShowDone((s) => !s)}
              style={{ alignSelf: "flex-start" }}
            >
              {showDone
                ? t("Erledigte ausblenden")
                : t("{{count}} erledigte/verworfene anzeigen", { count: done.length })}
            </Button>
            {showDone && done.map((wv) => <WiedervorlageCard key={wv.id} wv={wv} />)}
          </>
        )}
      </Stack>
      <WiedervorlageForm
        opened={editing.open}
        wiedervorlage={editing.wv}
        documentId={doc.id}
        onClose={() => setEditing({ open: false, wv: null })}
      />
    </Paper>
  );
}
