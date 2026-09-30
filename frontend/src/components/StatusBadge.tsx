import { Badge, Group, Loader, Tooltip } from "@mantine/core";
import type { DocumentItem } from "../api/client";
import { classificationLabels, formatPercent, stageLabels } from "../lib/format";

/** Verarbeitungs- bzw. Einordnungsstatus eines Dokuments als kompaktes Badge. */
export function DocumentStatusBadge({ doc }: { doc: DocumentItem }) {
  if (doc.ocr_status === "pending") {
    return (
      <Badge color="gray" variant="light" leftSection={<Loader size={10} color="gray" />}>
        Texterkennung
      </Badge>
    );
  }
  if (doc.ocr_status === "failed") {
    return (
      <Tooltip label="Der Text konnte nicht erkannt werden – das Dokument lässt sich trotzdem manuell einordnen.">
        <Badge color="red" variant="light">
          OCR fehlgeschlagen
        </Badge>
      </Tooltip>
    );
  }
  const info = classificationLabels[doc.classification_status] ?? { label: doc.classification_status, color: "gray" };
  const details = [
    doc.classification_stage ? stageLabels[doc.classification_stage] : null,
    formatPercent(doc.classification_confidence) || null,
  ]
    .filter(Boolean)
    .join(" · ");
  const badge = (
    <Badge
      color={info.color}
      variant="light"
      leftSection={doc.classification_status === "pending" ? <Loader size={10} color={info.color} /> : undefined}
    >
      {info.label}
    </Badge>
  );
  return details ? <Tooltip label={details}>{badge}</Tooltip> : badge;
}

export function ExtractionHint({ doc }: { doc: DocumentItem }) {
  if (doc.extraction_status !== "pending" || doc.ocr_status !== "done") return null;
  return (
    <Group gap={4}>
      <Loader size={10} />
      <Badge variant="transparent" color="gray" size="sm" px={0}>
        Metadaten werden gelesen
      </Badge>
    </Group>
  );
}
