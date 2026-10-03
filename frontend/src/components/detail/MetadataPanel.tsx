import {
  ActionIcon,
  Badge,
  Button,
  Code,
  CopyButton,
  Group,
  NumberInput,
  Paper,
  SegmentedControl,
  Select,
  Switch,
  Stack,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { IconCheck, IconCopy, IconFolder, IconWand } from "@tabler/icons-react";
import { useEffect } from "react";
import type { DocumentDetail, Schemas } from "../../api/client";
import { usePatchDocument, useProperties, useUpdateDocument } from "../../api/queries";
import { notifyError, notifySuccess } from "../../lib/notify";
import { ExtractionHint } from "../StatusBadge";

interface Values {
  title: string;
  subject: string;
  document_date: string | null;
  issuer: string;
  amount: number | string;
  property_id: string | null;
  original_present: Schemas["OriginalPresent"];
  original_location: string;
}

function valuesOf(doc: DocumentDetail): Values {
  return {
    title: doc.title,
    subject: doc.subject ?? "",
    document_date: doc.document_date,
    issuer: doc.issuer ?? "",
    amount: doc.amount ?? "",
    property_id: doc.property_id ?? null,
    original_present: doc.original_present,
    original_location: doc.original_location ?? "",
  };
}

/**
 * Titel, Betreff, Datum, Aussteller, Betrag, Objekt und Papier-Original. Leere Felder fuellt die KI.
 * Der Titel entsteht automatisch aus "Betreff – Absender", bis man ihn selbst aendert.
 */
export function MetadataPanel({ doc, readOnly = false }: { doc: DocumentDetail; readOnly?: boolean }) {
  const update = useUpdateDocument(doc.id);
  const setInvoice = usePatchDocument();
  const properties = useProperties();
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
  }, [doc.updated_at, doc.files[0]?.path]);

  const submit = form.onSubmit(async (values) => {
    // Nur geaenderte Felder schicken - ein mitgeschickter Titel wuerde sonst als "selbst vergeben" gelten
    const body: Schemas["DocumentUpdateRequest"] = {};
    if (form.isDirty("title")) body.title = values.title.trim();
    if (form.isDirty("subject")) body.subject = values.subject.trim() || null;
    if (form.isDirty("document_date")) body.document_date = values.document_date || null;
    if (form.isDirty("issuer")) body.issuer = values.issuer.trim() || null;
    if (form.isDirty("amount")) body.amount = values.amount === "" ? null : Number(values.amount);
    if (form.isDirty("property_id")) body.property_id = values.property_id;
    if (form.isDirty("original_present") || form.isDirty("original_location")) {
      body.original_present = values.original_present;
      body.original_location = values.original_present === "ja" ? values.original_location.trim() || null : null;
    }
    try {
      const saved = await update.mutateAsync(body);
      form.setValues(valuesOf(saved as DocumentDetail));
      form.resetDirty(valuesOf(saved as DocumentDetail));
      notifySuccess("Gespeichert");
    } catch (e) {
      notifyError(e, "Speichern fehlgeschlagen");
    }
  });

  async function autoTitle() {
    try {
      await update.mutateAsync({ title_locked: false });
      form.resetDirty();
      notifySuccess("Titel wird wieder automatisch gebildet");
    } catch (e) {
      notifyError(e);
    }
  }

  const path = doc.files[0]?.path;
  const propertyOptions = (properties.data ?? []).map((p) => ({ value: p.id, label: p.name }));

  return (
    <Paper withBorder p="md" radius="md">
      <form onSubmit={submit}>
        <Stack gap="sm">
          <Group justify="space-between">
            <Title order={4}>Angaben</Title>
            <ExtractionHint doc={doc} />
          </Group>
          <TextInput
            label={
              <Group gap={6} component="span">
                Titel
                {doc.title_locked ? (
                  <Badge size="xs" variant="light" color="gray">
                    eigener Titel
                  </Badge>
                ) : (
                  <Tooltip label="Wird aus Betreff und Absender gebildet">
                    <Badge size="xs" variant="light" leftSection={<IconWand size={10} />}>
                      automatisch
                    </Badge>
                  </Tooltip>
                )}
              </Group>
            }
            disabled={readOnly}
            rightSectionWidth={doc.title_locked && !readOnly ? 36 : undefined}
            rightSection={
              doc.title_locked && !readOnly ? (
                <Tooltip label="Titel wieder automatisch bilden">
                  <ActionIcon variant="subtle" onClick={() => void autoTitle()} aria-label="Automatisch benennen">
                    <IconWand size={16} />
                  </ActionIcon>
                </Tooltip>
              ) : undefined
            }
            {...form.getInputProps("title")}
          />
          <TextInput
            label="Betreff"
            placeholder="z. B. Rechnung Heizungswartung"
            description="Grundlage für Titel und Dateinamen"
            disabled={readOnly}
            {...form.getInputProps("subject")}
          />
          <Group grow align="flex-start">
            <DateInput
              label="Dokumentdatum"
              valueFormat="DD.MM.YYYY"
              clearable
              disabled={readOnly}
              {...form.getInputProps("document_date")}
            />
            {doc.is_invoice !== false && (
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
            )}
          </Group>
          <Switch
            label="Ist eine Rechnung"
            description={
              doc.is_invoice === false
                ? "Kein Betrag, keine Zahlung – Zahlungsfristen sind normale Termine"
                : doc.is_invoice_locked
                  ? "von Ihnen festgelegt"
                  : doc.is_invoice
                    ? "von der KI erkannt"
                    : "noch nicht bestimmt"
            }
            checked={
              doc.is_invoice !== false && (doc.is_invoice === true || doc.amount !== null || !!doc.payment_status)
            }
            disabled={readOnly || setInvoice.isPending}
            onChange={(e) =>
              setInvoice.mutate(
                { id: doc.id, body: { is_invoice: e.currentTarget.checked } },
                {
                  onSuccess: (_, v) =>
                    notifySuccess(v.body.is_invoice ? "Als Rechnung markiert" : "Als „Keine Rechnung“ markiert"),
                  onError: (err) => notifyError(err),
                },
              )
            }
          />
          <TextInput
            label="Aussteller"
            placeholder="z. B. Stadtwerke"
            disabled={readOnly}
            {...form.getInputProps("issuer")}
          />
          <Select
            label="Objekt"
            description="Haus oder Wohnung, zu der das Dokument gehört"
            placeholder="keinem Objekt zugeordnet"
            data={propertyOptions}
            clearable
            searchable
            disabled={readOnly}
            nothingFoundMessage="Objekte entstehen automatisch aus erkannten Adressen"
            {...form.getInputProps("property_id")}
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
              <Button variant="default" onClick={() => form.reset()}>
                Verwerfen
              </Button>
              <Button type="submit" loading={update.isPending}>
                Speichern
              </Button>
            </Group>
          )}
          {path && (
            <Group gap={6} wrap="nowrap" align="flex-start">
              <IconFolder size={16} color="var(--mantine-color-dimmed)" style={{ flexShrink: 0, marginTop: 2 }} />
              <Code style={{ overflowWrap: "anywhere", whiteSpace: "normal", flex: 1 }} fz="xs">
                {path}
              </Code>
              <CopyButton value={path}>
                {({ copied, copy }) => (
                  <Tooltip label={copied ? "Kopiert" : "Ablageort kopieren"}>
                    <ActionIcon variant="subtle" size="sm" onClick={copy} aria-label="Ablageort kopieren">
                      {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
                    </ActionIcon>
                  </Tooltip>
                )}
              </CopyButton>
            </Group>
          )}
        </Stack>
      </form>
    </Paper>
  );
}
