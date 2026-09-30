import { Alert, Button, Center, Image, Loader, Paper, Stack, Text } from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { IconExternalLink, IconFileOff } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { fetchDocumentFile, type DocumentDetail } from "../api/client";

/**
 * Vorschau der Originaldatei. Die Datei wird mit Anmeldung geladen und als Blob-URL angezeigt
 * (ein normaler <img src>/<iframe src> koennte kein Token mitschicken).
 * Handy-Browser zeigen PDFs meist nicht eingebettet an - dort gibt es einen "Oeffnen"-Knopf.
 */
export function DocumentPreview({ doc }: { doc: DocumentDetail }) {
  const isMobile = useMediaQuery("(max-width: 48em)") ?? false;
  const file = doc.files[0];
  const blob = useQuery({
    queryKey: ["document", doc.id, "file", file?.id],
    queryFn: () => fetchDocumentFile(doc.id),
    enabled: Boolean(file),
    staleTime: Infinity,
  });
  const url = useObjectUrl(blob.data);

  if (!file) {
    return <EmptyPreview text="Keine Datei vorhanden" />;
  }
  if (blob.isPending) {
    return (
      <Center h={isMobile ? 240 : 600}>
        <Loader />
      </Center>
    );
  }
  if (blob.isError || !url) {
    return (
      <Alert color="red" icon={<IconFileOff />}>
        Vorschau konnte nicht geladen werden: {blob.error?.message}
      </Alert>
    );
  }

  const isPdf = file.mime_type === "application/pdf";
  const isImage = file.mime_type.startsWith("image/") && !/hei[cf]|tiff/.test(file.mime_type);

  if (isImage) {
    return (
      <Paper withBorder p={4} radius="md">
        <Image src={url} alt={doc.title} radius="sm" fit="contain" mah={isMobile ? 480 : 800} />
      </Paper>
    );
  }
  if (isPdf && !isMobile) {
    return (
      <Paper withBorder radius="md" style={{ overflow: "hidden" }}>
        <iframe src={url} title={doc.title} style={{ width: "100%", height: "75vh", border: 0, display: "block" }} />
      </Paper>
    );
  }
  return (
    <EmptyPreview text={isPdf ? "PDF-Dokument" : `Keine Vorschau für ${file.mime_type}`}>
      <Button component="a" href={url} target="_blank" rel="noopener" leftSection={<IconExternalLink size={16} />}>
        Datei öffnen
      </Button>
    </EmptyPreview>
  );
}

function EmptyPreview({ text, children }: { text: string; children?: ReactNode }) {
  return (
    <Paper withBorder radius="md" p="xl">
      <Stack align="center" gap="sm">
        <IconFileOff size={40} color="var(--mantine-color-dimmed)" />
        <Text c="dimmed">{text}</Text>
        {children}
      </Stack>
    </Paper>
  );
}

function useObjectUrl(blob?: Blob): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) return;
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);
  return url;
}
