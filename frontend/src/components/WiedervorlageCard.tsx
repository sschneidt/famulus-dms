import { ActionIcon, Anchor, Badge, Blockquote, Button, Group, Menu, Paper, Stack, Text, Tooltip } from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconCheck, IconDots, IconEdit, IconFileText, IconRepeat, IconTrash, IconX } from "@tabler/icons-react";
import { Link } from "react-router";
import type { Wiedervorlage } from "../api/client";
import { useDeleteWiedervorlage, useSetPayment, useWiedervorlageAction } from "../api/queries";
import { isPaymentNote } from "../lib/payments";
import { PaidButton } from "./PaidButton";
import { formatDate, formatDateTime, formatPercent, recurrenceText, relativeDue, sourceLabels } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

interface Props {
  wv: Wiedervorlage;
  onEdit?(wv: Wiedervorlage): void;
  /** Link zum Dokument anzeigen (in der Gesamtuebersicht) */
  showDocument?: boolean;
}

/** Ein Termin/eine Wiedervorlage mit den passenden Aktionen je nach Status. */
export function WiedervorlageCard({ wv, onEdit, showDocument = false }: Props) {
  const action = useWiedervorlageAction();
  const remove = useDeleteWiedervorlage();
  const due = relativeDue(wv.due_date);
  const active = wv.status === "offen" || wv.status === "vorgeschlagen";
  const overdue = active && due.overdue;
  const setPayment = useSetPayment();
  // "Bezahlt" nur bei Rechnungen - bei "Keine Rechnung" ist eine Zahlungsfrist ein normaler Termin
  const payment = isPaymentNote(wv.note) && wv.document_is_invoice !== false;
  const busy = action.isPending || remove.isPending || setPayment.isPending;

  async function run(kind: "confirm" | "reject" | "complete", paidOn?: string) {
    try {
      const result = await action.mutateAsync({ id: wv.id, action: kind, paidOn });
      if (kind === "complete") {
        const next = (result as { next?: Wiedervorlage | null }).next;
        const done = paidOn ? `Bezahlt am ${formatDate(paidOn)}` : "Erledigt";
        notifySuccess(next ? `${done} – nächster Termin am ${formatDate(next.due_date)}` : done);
      } else {
        notifySuccess(kind === "confirm" ? "Termin übernommen" : "Vorschlag verworfen");
      }
    } catch (e) {
      notifyError(e);
    }
  }

  function confirmDelete() {
    modals.openConfirmModal({
      title: "Termin löschen?",
      children: <Text size="sm">„{wv.note}" wird endgültig gelöscht.</Text>,
      labels: { confirm: "Löschen", cancel: "Abbrechen" },
      confirmProps: { color: "red" },
      onConfirm: () =>
        remove.mutate(wv.id, {
          onSuccess: () => notifySuccess("Termin gelöscht"),
          onError: (e) => notifyError(e),
        }),
    });
  }

  return (
    <Paper
      withBorder
      p="sm"
      radius="md"
      style={overdue ? { borderLeft: "4px solid var(--mantine-color-red-6)" } : undefined}
      data-testid="wiedervorlage"
      data-overdue={overdue || undefined}
    >
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Stack gap={2} style={{ minWidth: 0 }}>
            <Group gap={6}>
              <Text fw={600}>{formatDate(wv.due_date)}</Text>
              {active && (
                <Text size="sm" c={overdue ? "red" : "dimmed"} fw={overdue ? 600 : undefined}>
                  {due.label}
                </Text>
              )}
            </Group>
            <Text size="sm" style={{ overflowWrap: "anywhere" }}>
              {wv.note}
            </Text>
          </Stack>
          {active && (
            <Menu position="bottom-end" withinPortal>
              <Menu.Target>
                <ActionIcon variant="subtle" color="gray" aria-label="Weitere Aktionen" disabled={busy}>
                  <IconDots size={16} />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                {onEdit && (
                  <Menu.Item leftSection={<IconEdit size={14} />} onClick={() => onEdit(wv)}>
                    Bearbeiten
                  </Menu.Item>
                )}
                <Menu.Item leftSection={<IconTrash size={14} />} color="red" onClick={confirmDelete}>
                  Löschen
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          )}
        </Group>

        <Group gap={6}>
          <Badge
            size="sm"
            variant="light"
            color={wv.source === "ai_suggested" ? "violet" : wv.source === "retention_rule" ? "teal" : "gray"}
          >
            {sourceLabels[wv.source] ?? wv.source}
            {wv.source === "ai_suggested" && wv.confidence !== null ? ` ${formatPercent(wv.confidence)}` : ""}
          </Badge>
          {wv.recurrence !== "none" && (
            <Badge size="sm" variant="light" leftSection={<IconRepeat size={12} />}>
              {recurrenceText(wv.recurrence, wv.recurrence_interval_months)}
            </Badge>
          )}
          {wv.status === "erledigt" && (
            <Badge size="sm" color="green" variant="light">
              erledigt {formatDateTime(wv.completed_at)}
            </Badge>
          )}
          {wv.status === "verworfen" && (
            <Badge size="sm" color="gray" variant="light">
              verworfen
            </Badge>
          )}
          {showDocument && (
            <Anchor component={Link} to={`/dokumente/${wv.document_id}`} size="sm">
              <Group gap={4} wrap="nowrap">
                <IconFileText size={14} />
                {wv.document_title ?? "Dokument"}
              </Group>
            </Anchor>
          )}
        </Group>

        {wv.status === "vorgeschlagen" && wv.source_snippet && (
          <Tooltip label="Fundstelle im Dokumenttext" position="top-start">
            <Blockquote p="xs" fz="sm" color="violet" style={{ fontStyle: "italic" }}>
              {wv.source_snippet}
            </Blockquote>
          </Tooltip>
        )}

        {wv.status === "vorgeschlagen" && (
          <Group gap="xs">
            <Button
              size="xs"
              leftSection={<IconCheck size={14} />}
              onClick={() => void run("confirm")}
              loading={action.isPending}
            >
              Übernehmen
            </Button>
            {onEdit && (
              <Button size="xs" variant="default" leftSection={<IconEdit size={14} />} onClick={() => onEdit(wv)}>
                Anpassen
              </Button>
            )}
            {payment && (
              <PaidButton
                label="Schon bezahlt"
                variant="default"
                color="gray"
                loading={setPayment.isPending}
                onConfirm={async (paidOn) => {
                  try {
                    await setPayment.mutateAsync({ documentId: wv.document_id, status: "bezahlt", paidOn });
                    notifySuccess(`Bezahlt am ${formatDate(paidOn)}`);
                  } catch (e) {
                    notifyError(e);
                  }
                }}
              />
            )}
            <Button
              size="xs"
              variant="subtle"
              color="gray"
              leftSection={<IconX size={14} />}
              onClick={() => void run("reject")}
              disabled={busy}
            >
              Verwerfen
            </Button>
          </Group>
        )}
        {wv.status === "offen" && payment && (
          <Group gap="xs">
            <PaidButton
              label="Bezahlt"
              variant={overdue ? "filled" : "light"}
              loading={action.isPending}
              onConfirm={(paidOn) => run("complete", paidOn)}
            />
          </Group>
        )}
        {wv.status === "offen" && !payment && (
          <Group gap="xs">
            <Button
              size="xs"
              variant={overdue ? "filled" : "light"}
              color="green"
              leftSection={<IconCheck size={14} />}
              onClick={() => void run("complete")}
              loading={action.isPending}
            >
              Erledigt
            </Button>
          </Group>
        )}
      </Stack>
    </Paper>
  );
}
