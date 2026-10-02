import {
  ActionIcon,
  Alert,
  Button,
  Group,
  Modal,
  Progress,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
} from "@mantine/core";
import { Dropzone, type FileWithPath } from "@mantine/dropzone";
import { useMediaQuery } from "@mantine/hooks";
import { IconArrowDown, IconArrowUp, IconCamera, IconFile, IconPhoto, IconUpload, IconX } from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { uploadDocument, type Schemas } from "../api/client";
import { notifyError, notifySuccess } from "../lib/notify";

const ACCEPTED_TYPES = {
  "application/pdf": [".pdf"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
  "image/tiff": [".tif", ".tiff"],
  "image/webp": [".webp"],
  "image/heic": [".heic"],
  "image/heif": [".heif"],
};
const MAX_SIZE = 50 * 1024 * 1024;

export interface PendingFile {
  file: File;
  source: Schemas["DocumentSource"];
}

interface Props {
  opened: boolean;
  onClose(): void;
  /** z. B. ein gerade mit der Kamera aufgenommenes Foto */
  initialFiles?: PendingFile[];
}

/**
 * Dokumente hochladen: Dateien ziehen/auswaehlen oder (am Handy) direkt fotografieren.
 * Jede Datei wird ein eigenes Dokument; OCR und Einordnung laufen danach im Hintergrund.
 */
export function UploadModal({ opened, onClose, initialFiles }: Props) {
  const isMobile = useMediaQuery("(max-width: 48em)") ?? false;
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      opened={opened}
      onClose={busy ? () => undefined : onClose}
      title="Dokumente hochladen"
      size="lg"
      fullScreen={isMobile}
      closeOnClickOutside={!busy}
    >
      {/* Inhalt wird beim Schliessen verworfen -> beim naechsten Oeffnen frischer Zustand */}
      <UploadForm initialFiles={initialFiles} onClose={onClose} onBusyChange={setBusy} isMobile={isMobile} />
    </Modal>
  );
}

function UploadForm({
  initialFiles,
  onClose,
  onBusyChange,
  isMobile,
}: {
  initialFiles?: PendingFile[];
  onClose(): void;
  onBusyChange(busy: boolean): void;
  isMobile: boolean;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const cameraInput = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<PendingFile[]>(initialFiles ?? []);
  const [title, setTitle] = useState("");
  const [original, setOriginal] = useState<Schemas["OriginalPresent"]>("unbekannt");
  const [location, setLocation] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [rejected, setRejected] = useState<string | null>(null);

  const addFiles = (added: File[], source: Schemas["DocumentSource"]) =>
    setFiles((current) => [...current, ...added.map((file) => ({ file, source }))]);

  const busy = progress !== null;
  useEffect(() => onBusyChange(busy), [busy, onBusyChange]);

  // Mehrere Dateien: ein Dokument mit mehreren Seiten oder einzelne Dokumente?
  // Vorschlag: Fotos gehoeren meist zusammen (zweiseitiger Brief), PDFs sind meist getrennte Scans.
  const [combineChoice, setCombineChoice] = useState<boolean | null>(null);
  const combinable = files.length > 1 && files.every((f) => isPageFile(f.file));
  const combine = combinable && (combineChoice ?? files.every((f) => f.file.type.startsWith("image/")));

  function move(index: number, delta: number) {
    setFiles((current) => {
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(index + delta, 0, item);
      return next;
    });
  }

  async function submit() {
    setProgress(0);
    const created: string[] = [];
    try {
      if (combine) {
        const doc = await uploadDocument(
          files.map((f) => f.file),
          {
            title: title.trim() || undefined,
            source: files.some((f) => f.source === "photo_app") ? "photo_app" : "upload",
            originalPresent: original,
            originalLocation: original === "ja" ? location.trim() || undefined : undefined,
          },
        );
        notifySuccess(`Dokument mit ${files.length} Seiten hochgeladen – Texterkennung läuft im Hintergrund.`);
        onClose();
        navigate(`/dokumente/${doc.id}`);
        return;
      }
      for (const [index, pending] of files.entries()) {
        const doc = await uploadDocument(pending.file, {
          title: files.length === 1 ? title.trim() || undefined : undefined,
          source: pending.source,
          originalPresent: original,
          originalLocation: original === "ja" ? location.trim() || undefined : undefined,
        });
        created.push(doc.id);
        setProgress(((index + 1) / files.length) * 100);
      }
      notifySuccess(
        created.length === 1
          ? "Dokument hochgeladen – Texterkennung läuft im Hintergrund."
          : `${created.length} Dokumente hochgeladen – Texterkennung läuft im Hintergrund.`,
      );
      onClose();
      if (created.length === 1) navigate(`/dokumente/${created[0]}`);
      else navigate("/");
    } catch (e) {
      notifyError(
        e,
        created.length ? `Nur ${created.length} von ${files.length} hochgeladen` : "Hochladen fehlgeschlagen",
      );
      setFiles((current) => current.slice(created.length));
      setProgress(null);
    } finally {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    }
  }

  return (
    <Stack>
      <input
        ref={cameraInput}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        data-testid="camera-input"
        onChange={(e) => {
          addFiles(Array.from(e.currentTarget.files ?? []), "photo_app");
          e.currentTarget.value = "";
        }}
      />

      <Dropzone
        onDrop={(dropped: FileWithPath[]) => {
          setRejected(null);
          addFiles(dropped, "upload");
        }}
        onReject={(rejections) =>
          setRejected(
            rejections
              .map(
                (r) =>
                  `${r.file.name}: ${r.errors[0]?.code === "file-too-large" ? "zu groß (max. 50 MB)" : "Dateityp nicht unterstützt"}`,
              )
              .join(", "),
          )
        }
        accept={ACCEPTED_TYPES}
        maxSize={MAX_SIZE}
        disabled={busy}
      >
        <Group justify="center" gap="md" mih={isMobile ? 90 : 140} style={{ pointerEvents: "none" }}>
          <Dropzone.Accept>
            <IconUpload size={44} color="var(--mantine-color-blue-6)" />
          </Dropzone.Accept>
          <Dropzone.Reject>
            <IconX size={44} color="var(--mantine-color-red-6)" />
          </Dropzone.Reject>
          <Dropzone.Idle>
            <IconFile size={44} color="var(--mantine-color-dimmed)" />
          </Dropzone.Idle>
          <div>
            <Text size="lg" inline>
              {isMobile ? "Datei auswählen" : "Dateien hierher ziehen oder klicken"}
            </Text>
            <Text size="sm" c="dimmed" mt={7}>
              PDF, JPG, PNG, TIFF, HEIC – bis 50 MB
            </Text>
          </div>
        </Group>
      </Dropzone>

      <Button
        variant="light"
        hiddenFrom="sm"
        leftSection={<IconCamera size={18} />}
        onClick={() => cameraInput.current?.click()}
        disabled={busy}
        size={isMobile ? "md" : "sm"}
      >
        {files.length > 0 ? "Weitere Seite fotografieren" : "Foto aufnehmen"}
      </Button>

      {rejected && (
        <Alert color="red" withCloseButton onClose={() => setRejected(null)}>
          {rejected}
        </Alert>
      )}

      {combinable && (
        <SegmentedControl
          fullWidth
          value={combine ? "eins" : "einzeln"}
          onChange={(v) => setCombineChoice(v === "eins")}
          disabled={busy}
          data={[
            { value: "eins", label: `Ein Dokument (${files.length} Seiten)` },
            { value: "einzeln", label: `${files.length} einzelne Dokumente` },
          ]}
        />
      )}

      {files.length > 0 && (
        <Stack gap={6}>
          {files.map((pending, index) => (
            <Group key={`${pending.file.name}-${index}`} justify="space-between" wrap="nowrap">
              <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                {combine && (
                  <Text size="xs" c="dimmed" w={52} style={{ flexShrink: 0 }}>
                    Seite {index + 1}
                  </Text>
                )}
                <ThemeIcon variant="light" size="sm">
                  {pending.file.type.startsWith("image/") ? <IconPhoto size={14} /> : <IconFile size={14} />}
                </ThemeIcon>
                <Text size="sm" truncate>
                  {pending.file.name || "Foto"}
                </Text>
                <Text size="xs" c="dimmed" style={{ flexShrink: 0 }}>
                  {formatSize(pending.file.size)}
                </Text>
              </Group>
              <Group gap={0} wrap="nowrap">
                {combine && (
                  <>
                    <ActionIcon
                      variant="subtle"
                      color="gray"
                      disabled={busy || index === 0}
                      onClick={() => move(index, -1)}
                      aria-label={`Seite ${index + 1} nach oben`}
                    >
                      <IconArrowUp size={16} />
                    </ActionIcon>
                    <ActionIcon
                      variant="subtle"
                      color="gray"
                      disabled={busy || index === files.length - 1}
                      onClick={() => move(index, 1)}
                      aria-label={`Seite ${index + 1} nach unten`}
                    >
                      <IconArrowDown size={16} />
                    </ActionIcon>
                  </>
                )}
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  disabled={busy}
                  onClick={() => setFiles((current) => current.filter((_, i) => i !== index))}
                  aria-label={`${pending.file.name} entfernen`}
                >
                  <IconX size={16} />
                </ActionIcon>
              </Group>
            </Group>
          ))}
        </Stack>
      )}

      {(files.length === 1 || combine) && (
        <TextInput
          label="Titel (optional)"
          placeholder={combine ? "wird automatisch vergeben" : files[0].file.name}
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
          disabled={busy}
        />
      )}

      <div>
        <Text size="sm" fw={500} mb={4}>
          Papier-Original aufbewahrt?
        </Text>
        <SegmentedControl
          fullWidth
          value={original}
          onChange={(v) => setOriginal(v as Schemas["OriginalPresent"])}
          disabled={busy}
          data={[
            { value: "ja", label: "Ja" },
            { value: "nein", label: "Nein" },
            { value: "unbekannt", label: "Weiß nicht" },
          ]}
        />
      </div>
      {original === "ja" && (
        <TextInput
          label="Wo liegt das Original?"
          placeholder="z. B. Ordner Versicherungen"
          value={location}
          onChange={(e) => setLocation(e.currentTarget.value)}
          disabled={busy}
        />
      )}

      {progress !== null && <Progress value={progress} animated />}

      <Group justify="flex-end">
        <Button variant="default" onClick={onClose} disabled={busy}>
          Abbrechen
        </Button>
        <Button
          onClick={() => void submit()}
          disabled={files.length === 0}
          loading={busy}
          leftSection={<IconUpload size={16} />}
        >
          {combine
            ? "Als ein Dokument hochladen"
            : files.length > 1
              ? `${files.length} Dokumente hochladen`
              : "Hochladen"}
        </Button>
      </Group>
    </Stack>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

function isPageFile(file: File): boolean {
  return (
    file.type === "application/pdf" ||
    file.type.startsWith("image/") ||
    /\.(pdf|jpe?g|png|tiff?|webp|hei[cf])$/i.test(file.name)
  );
}
