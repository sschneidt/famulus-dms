import { Button, Group, NumberInput, Paper, SegmentedControl, Stack, Text, TextInput, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useEffect } from "react";
import type { DocumentDetail, Schemas } from "../../api/client";
import { useUpdateDocument } from "../../api/queries";
import { notifyError, notifySuccess } from "../../lib/notify";
import { ExtractionHint } from "../StatusBadge";

interface Values {
  title: string;
  document_date: string | null;
  issuer: string;
  amount: number | string;
  original_present: Schemas["OriginalPresent"];
  original_location: string;
}

function valuesOf(doc: DocumentDetail): Values {
  return {
    title: doc.title,
    document_date: doc.document_date,
    issuer: doc.issuer ?? "",
    amount: doc.amount ?? "",
    original_present: doc.original_present,
    original_location: doc.original_location ?? "",
  };
}

/** Titel, Datum, Aussteller, Betrag und Papier-Original. Leere Felder fuellt die KI automatisch. */
export function MetadataPanel({ doc, readOnly = false }: { doc: DocumentDetail; readOnly?: boolean }) {
  const update = useUpdateDocument(doc.id);
  const form = useForm<Values>({
    initialValues: valuesOf(doc),
    validate: {
      title: (v) => (v.trim() ? null : "Titel darf nicht leer sein"),
      amount: (v) => (v === "" || Number(v) >= 0 ? null : "Betrag darf nicht negativ sein"),
    },
  });

  // Neue Werte vom Server (z. B. KI hat Metadaten ergaenzt) uebernehmen, solange nichts bearbeitet wird
  useEffect(() => {
    if (!form.isDirty()) {
      form.setValues(valuesOf(doc));
      form.resetDirty(valuesOf(doc));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc.updated_at]);

  const submit = form.onSubmit(async (values) => {
    try {
      await update.mutateAsync({
        title: values.title.trim(),
        document_date: values.document_date || null,
        issuer: values.issuer.trim() || null,
        amount: values.amount === "" ? null : Number(values.amount),
        original_present: values.original_present,
        original_location: values.original_present === "ja" ? values.original_location.trim() || null : null,
      });
      form.resetDirty();
      notifySuccess("Gespeichert");
    } catch (e) {
      notifyError(e, "Speichern fehlgeschlagen");
    }
  });

  return (
    <Paper withBorder p="md" radius="md">
      <form onSubmit={submit}>
        <Stack gap="sm">
          <Group justify="space-between">
            <Title order={4}>Angaben</Title>
            <ExtractionHint doc={doc} />
          </Group>
          <TextInput label="Titel" disabled={readOnly} {...form.getInputProps("title")} />
          <Group grow align="flex-start">
            <DateInput
              label="Dokumentdatum"
              valueFormat="DD.MM.YYYY"
              clearable
              disabled={readOnly}
              {...form.getInputProps("document_date")}
            />
            <NumberInput
              label="Betrag"
              decimalSeparator=","
              thousandSeparator="."
              decimalScale={2}
              fixedDecimalScale
              min={0}
              suffix=" €"
              hideControls
              disabled={readOnly}
              {...form.getInputProps("amount")}
            />
          </Group>
          <TextInput
            label="Aussteller"
            placeholder="z. B. Stadtwerke"
            disabled={readOnly}
            {...form.getInputProps("issuer")}
          />
          <div>
            <Text size="sm" fw={500} mb={4}>
              Papier-Original
            </Text>
            <SegmentedControl
              fullWidth
              disabled={readOnly}
              data={[
                { value: "ja", label: "vorhanden" },
                { value: "nein", label: "entsorgt" },
                { value: "unbekannt", label: "unbekannt" },
              ]}
              {...form.getInputProps("original_present")}
            />
          </div>
          {form.values.original_present === "ja" && (
            <TextInput
              label="Aufbewahrungsort"
              placeholder="z. B. Ordner Versicherungen"
              disabled={readOnly}
              {...form.getInputProps("original_location")}
            />
          )}
          {!readOnly && form.isDirty() && (
            <Group justify="flex-end">
              <Button variant="default" onClick={() => form.setValues(valuesOf(doc))}>
                Verwerfen
              </Button>
              <Button type="submit" loading={update.isPending}>
                Speichern
              </Button>
            </Group>
          )}
        </Stack>
      </form>
    </Paper>
  );
}
