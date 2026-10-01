import { Alert, Anchor, Card, Center, Group, Loader, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconCash, IconConfetti } from "@tabler/icons-react";
import { Link } from "react-router";
import type { DocumentItem } from "../api/client";
import { useSetPayment, useUnpaid } from "../api/queries";
import { PaidButton } from "../components/PaidButton";
import { formatAmount, formatDate, relativeDue } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

/** Unbezahlte Rechnungen - die naechste Zahlungsfrist zuerst, mit Summe und "Bezahlt"-Knopf. */
export function UnpaidPage() {
  const unpaid = useUnpaid();

  return (
    <Stack>
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={2}>Unbezahlte Rechnungen</Title>
          <Text c="dimmed" size="sm">
            Überfällige zuerst. Mit „Bezahlt“ das Zahlungsdatum eintragen – die Zahlungsfrist wird dabei erledigt.
          </Text>
        </div>
        {unpaid.data && unpaid.data.total > 0 && (
          <Card withBorder padding="xs" radius="md">
            <Text size="xs" c="dimmed">
              {unpaid.data.total} {unpaid.data.total === 1 ? "Rechnung" : "Rechnungen"} offen
            </Text>
            <Text fw={700} size="lg" data-testid="unpaid-sum">
              {formatAmount(unpaid.data.total_amount)}
            </Text>
          </Card>
        )}
      </Group>

      {unpaid.isPending ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : unpaid.isError ? (
        <Alert color="red">{unpaid.error.message}</Alert>
      ) : unpaid.data.items.length === 0 ? (
        <Card withBorder padding="xl" radius="md">
          <Stack align="center" gap="xs">
            <ThemeIcon size={48} radius="xl" variant="light" color="green">
              <IconConfetti size={28} />
            </ThemeIcon>
            <Text fw={500}>Alles bezahlt</Text>
            <Text size="sm" c="dimmed">
              Es gibt keine offenen Rechnungen.
            </Text>
          </Stack>
        </Card>
      ) : (
        <Stack gap="xs">
          {unpaid.data.items.map((doc) => (
            <UnpaidCard key={doc.id} doc={doc} />
          ))}
        </Stack>
      )}
    </Stack>
  );
}

function UnpaidCard({ doc }: { doc: DocumentItem }) {
  const setPayment = useSetPayment();
  const due = doc.payment_due ? relativeDue(doc.payment_due) : null;

  return (
    <Card
      withBorder
      padding="sm"
      radius="md"
      style={due?.overdue ? { borderLeft: "4px solid var(--mantine-color-red-6)" } : undefined}
      data-testid="unpaid-item"
    >
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Group gap="sm" wrap="nowrap" align="flex-start" style={{ minWidth: 0 }}>
          <ThemeIcon variant="light" color={due?.overdue ? "red" : "orange"} visibleFrom="xs">
            <IconCash size={18} />
          </ThemeIcon>
          <div style={{ minWidth: 0 }}>
            <Anchor
              component={Link}
              to={`/dokumente/${doc.id}`}
              fw={500}
              c="var(--mantine-color-text)"
              style={{ overflowWrap: "anywhere" }}
            >
              {doc.title || "Ohne Titel"}
            </Anchor>
            <Text size="sm" c="dimmed">
              {[doc.issuer, doc.document_date ? `vom ${formatDate(doc.document_date)}` : null]
                .filter(Boolean)
                .join(" · ")}
            </Text>
            <Text size="sm" c={due?.overdue ? "red" : undefined} fw={due?.overdue ? 600 : undefined}>
              {doc.payment_due ? `fällig ${formatDate(doc.payment_due)} – ${due?.label}` : "ohne Zahlungsfrist"}
            </Text>
          </div>
        </Group>
        <Stack gap={6} align="flex-end" style={{ flexShrink: 0 }}>
          <Text fw={700} style={{ whiteSpace: "nowrap" }}>
            {formatAmount(doc.amount)}
          </Text>
          <PaidButton
            label="Bezahlt"
            variant={due?.overdue ? "filled" : "light"}
            loading={setPayment.isPending}
            onConfirm={async (paidOn) => {
              try {
                await setPayment.mutateAsync({ documentId: doc.id, status: "bezahlt", paidOn });
                notifySuccess(`„${doc.title}" bezahlt am ${formatDate(paidOn)}`);
              } catch (e) {
                notifyError(e);
              }
            }}
          />
        </Stack>
      </Group>
    </Card>
  );
}
