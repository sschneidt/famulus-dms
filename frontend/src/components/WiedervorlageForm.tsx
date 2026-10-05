import { Alert, Button, Group, Modal, NumberInput, Select, Stack, Textarea } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useMediaQuery } from "@mantine/hooks";
import dayjs from "dayjs";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { Wiedervorlage } from "../api/client";
import { useCreateWiedervorlage, useUpdateWiedervorlage } from "../api/queries";
import { dateInputFormat } from "../i18n";
import { recurrenceOptions } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

interface Props {
  opened: boolean;
  onClose(): void;
  documentId: string;
  /** vorhanden = bearbeiten, sonst neu anlegen */
  wiedervorlage?: Wiedervorlage | null;
}

type Recurrence = "none" | "monthly" | "yearly" | "custom_months";

interface Values {
  due_date: string | null;
  note: string;
  recurrence: Recurrence;
  recurrence_interval_months: number | string;
  reminder_lead_days: number | string;
}

export function WiedervorlageForm({ opened, onClose, documentId, wiedervorlage }: Props) {
  const isMobile = useMediaQuery("(max-width: 48em)") ?? false;
  const { t } = useTranslation();
  const create = useCreateWiedervorlage(documentId);
  const update = useUpdateWiedervorlage();
  const fromRetention = wiedervorlage?.source === "retention_rule";

  const form = useForm<Values>({
    initialValues: {
      due_date: dayjs().add(1, "month").format("YYYY-MM-DD"),
      note: "",
      recurrence: "none",
      recurrence_interval_months: 3,
      reminder_lead_days: 30,
    },
    validate: {
      due_date: (v) => (v ? null : t("Bitte ein Datum wählen")),
      note: (v) => (v.trim() ? null : t("Bitte beschreiben, worum es geht")),
      recurrence_interval_months: (v, values) =>
        values.recurrence !== "custom_months" || (Number(v) >= 1 && Number(v) <= 120) ? null : t("1 bis 120 Monate"),
      reminder_lead_days: (v) => (Number(v) >= 0 && Number(v) <= 3650 ? null : t("0 bis 3650 Tage")),
    },
  });

  useEffect(() => {
    if (!opened) return;
    if (wiedervorlage) {
      form.setValues({
        due_date: wiedervorlage.due_date,
        note: wiedervorlage.note,
        recurrence: wiedervorlage.recurrence as Recurrence,
        recurrence_interval_months: wiedervorlage.recurrence_interval_months ?? 3,
        reminder_lead_days: wiedervorlage.reminder_lead_days,
      });
    } else {
      form.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, wiedervorlage]);

  const submit = form.onSubmit(async (values) => {
    const body = {
      due_date: values.due_date!,
      note: values.note.trim(),
      recurrence: values.recurrence,
      recurrence_interval_months:
        values.recurrence === "custom_months" ? Number(values.recurrence_interval_months) : null,
      reminder_lead_days: Number(values.reminder_lead_days),
    };
    try {
      if (wiedervorlage) {
        const { due_date, ...rest } = body;
        await update.mutateAsync({ id: wiedervorlage.id, body: fromRetention ? rest : { due_date, ...rest } });
        notifySuccess(t("Termin gespeichert"));
      } else {
        await create.mutateAsync(body);
        notifySuccess(t("Termin angelegt"));
      }
      onClose();
    } catch (e) {
      notifyError(e, t("Speichern fehlgeschlagen"));
    }
  });

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={wiedervorlage ? t("Termin bearbeiten") : t("Neuer Termin")}
      fullScreen={isMobile}
    >
      <form onSubmit={submit}>
        <Stack>
          {fromRetention && (
            <Alert color="blue" variant="light">
              {t("Das Datum ergibt sich aus der Aufbewahrungsregel und dem Dokumentdatum.")}
            </Alert>
          )}
          <DateInput
            label={t("Fällig am")}
            valueFormat={dateInputFormat()}
            disabled={fromRetention}
            popoverProps={{ withinPortal: true }}
            {...form.getInputProps("due_date")}
          />
          <Textarea label={t("Worum geht es?")} autosize minRows={2} maxLength={1000} {...form.getInputProps("note")} />
          <Select
            label={t("Wiederholung")}
            allowDeselect={false}
            data={recurrenceOptions()}
            {...form.getInputProps("recurrence")}
          />
          {form.values.recurrence === "custom_months" && (
            <NumberInput
              label={t("Alle wie viele Monate?")}
              min={1}
              max={120}
              {...form.getInputProps("recurrence_interval_months")}
            />
          )}
          <NumberInput
            label={t("Erinnerung (Tage vorher)")}
            min={0}
            max={3650}
            {...form.getInputProps("reminder_lead_days")}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {t("Abbrechen")}
            </Button>
            <Button type="submit" loading={create.isPending || update.isPending}>
              {t("Speichern")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
