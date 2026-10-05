import { Button, Group, Paper, Select, Stack, Text, Title } from "@mantine/core";
import { IconCheck } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import type { DocumentDetail } from "../../api/client";
import { useAssignCategory } from "../../api/queries";
import { useCategoryOptions } from "../../lib/categories";
import { notifyError, notifySuccess } from "../../lib/notify";
import { DocumentStatusBadge } from "../StatusBadge";

/** Kategorie anzeigen, KI-Vorschlag bestaetigen oder korrigieren. */
export function CategoryPanel({ doc, readOnly = false }: { doc: DocumentDetail; readOnly?: boolean }) {
  const { t } = useTranslation();
  const options = useCategoryOptions();
  const assign = useAssignCategory();
  const unconfirmed = doc.classification_status === "needs_review" || doc.classification_status === "auto_assigned";

  async function choose(categoryId: string | null) {
    if (!categoryId) return;
    try {
      await assign.mutateAsync({ documentId: doc.id, categoryId });
      notifySuccess(categoryId === doc.category_id ? t("Kategorie bestätigt") : t("Kategorie geändert"));
    } catch (e) {
      notifyError(e, t("Kategorie konnte nicht gesetzt werden"));
    }
  }

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={4}>{t("Kategorie")}</Title>
          <DocumentStatusBadge doc={doc} />
        </Group>
        <Select
          data={options}
          value={doc.category_id}
          onChange={(v) => void choose(v)}
          placeholder={
            doc.classification_status === "pending" ? t("wird automatisch ermittelt …") : t("Kategorie wählen")
          }
          searchable
          allowDeselect={false}
          disabled={readOnly || assign.isPending}
          aria-label={t("Kategorie")}
        />
        {unconfirmed && doc.category_id && !readOnly && (
          <Group justify="space-between" wrap="nowrap">
            <Text size="sm" c="dimmed">
              {doc.classification_status === "needs_review"
                ? t("Die KI ist sich nicht sicher – bitte prüfen.")
                : t("Automatisch eingeordnet.")}
            </Text>
            <Button
              size="xs"
              leftSection={<IconCheck size={14} />}
              onClick={() => void choose(doc.category_id)}
              loading={assign.isPending}
              style={{ flexShrink: 0 }}
            >
              {t("Bestätigen")}
            </Button>
          </Group>
        )}
        {doc.classification_status === "needs_review" && !doc.category_id && (
          <Text size="sm" c="dimmed">
            {t("Keine passende Kategorie gefunden – bitte auswählen.")}
          </Text>
        )}
      </Stack>
    </Paper>
  );
}
