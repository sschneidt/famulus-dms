import { Loader, Paper, Stack, Text, Timeline, Title } from "@mantine/core";
import { IconRobot, IconUser } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useClassificationHistory } from "../../api/queries";
import { useCategoryNames } from "../../lib/categories";
import { formatDateTime, formatPercent, stageLabel } from "../../lib/format";

/** Wer hat wann welche Kategorie vergeben (KI oder Mensch) - Nachvollziehbarkeit. */
export function HistoryPanel({ documentId }: { documentId: string }) {
  const { t } = useTranslation();
  const history = useClassificationHistory(documentId);
  const categoryName = useCategoryNames();

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Title order={4}>{t("Verlauf")}</Title>
        {history.isPending ? (
          <Loader size="sm" />
        ) : !history.data?.length ? (
          <Text size="sm" c="dimmed">
            {t("Noch keine Einordnung.")}
          </Text>
        ) : (
          <Timeline bulletSize={22} lineWidth={2}>
            {history.data.map((event) => {
              const manual = event.stage === "manual";
              return (
                <Timeline.Item
                  key={event.id}
                  bullet={manual ? <IconUser size={12} /> : <IconRobot size={12} />}
                  title={
                    event.previous_category_id && event.previous_category_id !== event.new_category_id
                      ? `${categoryName(event.previous_category_id)} → ${categoryName(event.new_category_id)}`
                      : categoryName(event.new_category_id)
                  }
                >
                  <Text size="xs" c="dimmed">
                    {[stageLabel(event.stage), formatPercent(event.confidence), formatDateTime(event.created_at)]
                      .filter(Boolean)
                      .join(" · ")}
                  </Text>
                  {event.note && (
                    <Text size="sm" mt={2}>
                      {event.note}
                    </Text>
                  )}
                </Timeline.Item>
              );
            })}
          </Timeline>
        )}
      </Stack>
    </Paper>
  );
}
