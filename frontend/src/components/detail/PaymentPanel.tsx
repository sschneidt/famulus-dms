import { Badge, Button, Group, Paper, Stack, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { DocumentDetail } from "../../api/client";
import { usePatchDocument, useSetPayment } from "../../api/queries";
import { formatAmount, formatDate } from "../../lib/format";
import { notifyError, notifySuccess } from "../../lib/notify";
import { PaidButton } from "../PaidButton";

/** Zahlung einer Rechnung: offen / bezahlt am ... - nur bei Dokumenten mit Betrag oder Zahlungsfrist. */
export function PaymentPanel({ doc, readOnly = false }: { doc: DocumentDetail; readOnly?: boolean }) {
  const setPayment = useSetPayment();
  const setInvoice = usePatchDocument();
  const { t } = useTranslation();
  if (doc.is_invoice === false) return null;
  if (!doc.is_invoice && !doc.payment_status && doc.amount === null) return null;

  async function save(status: "offen" | "bezahlt" | null, paidOn?: string) {
    try {
      await setPayment.mutateAsync({ documentId: doc.id, status, paidOn });
      notifySuccess(
        status === "bezahlt"
          ? t("Als bezahlt markiert")
          : status === "offen"
            ? t("Als offen markiert")
            : t("Gespeichert"),
      );
    } catch (e) {
      notifyError(e);
    }
  }

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={4}>{t("Zahlung")}</Title>
          {doc.payment_status === "bezahlt" ? (
            <Badge color="green" variant="light">
              {t("bezahlt")}
            </Badge>
          ) : doc.payment_status === "offen" ? (
            <Badge color="orange" variant="light">
              {t("offen")}
            </Badge>
          ) : (
            <Badge color="gray" variant="light">
              {t("nicht erfasst")}
            </Badge>
          )}
        </Group>
        {doc.amount !== null && (
          <Text size="sm">
            {t("Betrag:")} <b>{formatAmount(doc.amount)}</b>
          </Text>
        )}
        {doc.payment_status === "bezahlt" && (
          <Text size="sm" c="dimmed">
            {doc.paid_assumed
              ? t("Automatisch angenommen – die Zahlungsfrist lag beim Einlesen mehr als 3 Monate zurück.")
              : doc.paid_on
                ? t("Bezahlt am {{date}}", { date: formatDate(doc.paid_on) })
                : t("Bezahlt (Datum unbekannt)")}
          </Text>
        )}
        {!readOnly && (
          <Group gap="xs">
            {doc.payment_status !== "bezahlt" ? (
              <PaidButton loading={setPayment.isPending} onConfirm={(d) => save("bezahlt", d)} />
            ) : (
              <>
                <PaidButton
                  label={doc.paid_on ? t("Datum ändern") : t("Zahlungsdatum eintragen")}
                  initial={doc.paid_on}
                  variant="default"
                  color="gray"
                  loading={setPayment.isPending}
                  onConfirm={(d) => save("bezahlt", d)}
                />
                <Button size="xs" variant="subtle" color="gray" onClick={() => void save("offen")}>
                  {t("Doch nicht bezahlt")}
                </Button>
              </>
            )}
            {!doc.payment_status && (
              <Button size="xs" variant="subtle" color="orange" onClick={() => void save("offen")}>
                {t("Als offen markieren")}
              </Button>
            )}
            <Button
              size="xs"
              variant="subtle"
              color="gray"
              loading={setInvoice.isPending}
              onClick={() =>
                setInvoice.mutate(
                  { id: doc.id, body: { is_invoice: false } },
                  {
                    onSuccess: () => notifySuccess(t("Als „Keine Rechnung“ markiert – Betrag und Zahlung entfernt")),
                    onError: (e) => notifyError(e),
                  },
                )
              }
            >
              {t("Keine Rechnung")}
            </Button>
          </Group>
        )}
      </Stack>
    </Paper>
  );
}
