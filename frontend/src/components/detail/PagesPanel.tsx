import {
  ActionIcon,
  Badge,
  Button,
  Card,
  FileButton,
  Group,
  Image,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconArrowLeft, IconArrowRight, IconCamera, IconCrop, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { addPages, api, call, fetchPageThumbnail, rectifyPage, type DocumentDetail } from "../../api/client";
import { isProcessing } from "../../lib/format";
import { notifyError, notifySuccess } from "../../lib/notify";

/**
 * Seiten eines Dokuments: Vorschaubilder, umsortieren, entfernen, Seiten hinzufuegen (Datei oder
 * Kamera). Nach jeder Aenderung werden Text und Angaben neu ausgewertet.
 */
export function PagesPanel({ doc, readOnly = false }: { doc: DocumentDetail; readOnly?: boolean }) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const camera = useRef<HTMLInputElement>(null);
  const count = doc.page_count ?? 1;
  const busy = isProcessing(doc);
  const version = doc.files[0]?.id + ":" + doc.updated_at;

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["document", doc.id] });
  const change = useMutation({
    mutationFn: async (
      action:
        | { kind: "add"; files: File[] }
        | { kind: "delete"; page: number }
        | { kind: "order"; order: number[] }
        | { kind: "rectify"; page: number },
    ) => {
      const path = { params: { path: { document_id: doc.id } } };
      if (action.kind === "add") return addPages(doc.id, action.files);
      if (action.kind === "rectify") return rectifyPage(doc.id, action.page);
      if (action.kind === "delete")
        return call(
          api.DELETE("/api/v1/documents/{document_id}/pages/{page}", {
            params: { path: { document_id: doc.id, page: action.page } },
          }),
        );
      return call(api.PUT("/api/v1/documents/{document_id}/pages/order", { ...path, body: { order: action.order } }));
    },
    onSuccess: (result, action) => {
      notifySuccess(
        action.kind === "add"
          ? t("Jetzt {{count}} Seiten – Text wird neu erkannt", { count: result.page_count })
          : action.kind === "delete"
            ? t("Seite entfernt")
            : action.kind === "rectify"
              ? t("Seite {{page}} zugeschnitten und gerade gerichtet – Text wird neu erkannt", { page: action.page })
              : t("Reihenfolge geändert"),
      );
      void refresh();
    },
    onError: (e, action) =>
      notifyError(
        e,
        action.kind === "rectify" ? t("Zuschneiden nicht möglich") : t("Seiten konnten nicht geändert werden"),
      ),
  });

  function move(page: number, delta: number) {
    const order = Array.from({ length: count }, (_, i) => i + 1);
    const [item] = order.splice(page - 1, 1);
    order.splice(page - 1 + delta, 0, item);
    change.mutate({ kind: "order", order });
  }

  function confirmDelete(page: number) {
    modals.openConfirmModal({
      title: t("Seite {{page}} entfernen?", { page }),
      children: <Text size="sm">{t("Die Seite wird aus dem Dokument gelöscht.")}</Text>,
      labels: { confirm: t("Entfernen"), cancel: t("Abbrechen") },
      confirmProps: { color: "red" },
      onConfirm: () => change.mutate({ kind: "delete", page }),
    });
  }

  const locked = readOnly || busy || change.isPending;
  const canPage = doc.files[0] && /pdf|image/.test(doc.files[0].mime_type);

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Group gap="xs">
            <Title order={4}>{t("Seiten")}</Title>
            <Badge variant="light" color="gray">
              {count}
            </Badge>
            {(busy || change.isPending) && <Loader size="xs" />}
          </Group>
          {!readOnly && canPage && (
            <Group gap="xs">
              <FileButton
                multiple
                accept="application/pdf,image/*"
                onChange={(files) => files.length && change.mutate({ kind: "add", files })}
                disabled={locked}
              >
                {(props) => (
                  <Button {...props} size="xs" variant="light" leftSection={<IconPlus size={14} />} disabled={locked}>
                    {t("Seite hinzufügen")}
                  </Button>
                )}
              </FileButton>
              <Button
                size="xs"
                variant="light"
                hiddenFrom="sm"
                leftSection={<IconCamera size={14} />}
                disabled={locked}
                onClick={() => camera.current?.click()}
              >
                {t("Fotografieren")}
              </Button>
              <input
                ref={camera}
                type="file"
                accept="image/*"
                capture="environment"
                hidden
                onChange={(e) => {
                  const files = Array.from(e.currentTarget.files ?? []);
                  e.currentTarget.value = "";
                  if (files.length) change.mutate({ kind: "add", files });
                }}
              />
            </Group>
          )}
        </Group>
        {busy && (
          <Text size="xs" c="dimmed">
            {t("Text wird erkannt – Seiten lassen sich danach wieder bearbeiten.")}
          </Text>
        )}
        {canPage && (
          <SimpleGrid cols={{ base: 3, xs: 4, md: 4 }} spacing="xs">
            {Array.from({ length: count }, (_, i) => i + 1).map((page) => (
              <Card key={`${version}-${page}`} withBorder padding={4} radius="sm" data-testid="page">
                <Thumbnail documentId={doc.id} page={page} version={version} />
                <Group justify="space-between" gap={0} mt={4} wrap="nowrap">
                  <Text size="xs" c="dimmed" pl={2}>
                    {page}
                  </Text>
                  {!readOnly && (
                    <Group gap={0} wrap="nowrap">
                      <Tooltip label={t("zuschneiden & gerade richten")}>
                        <ActionIcon
                          size="sm"
                          variant="subtle"
                          color="gray"
                          disabled={locked}
                          onClick={() => change.mutate({ kind: "rectify", page })}
                          aria-label={t("Seite {{page}} zuschneiden", { page })}
                        >
                          <IconCrop size={14} />
                        </ActionIcon>
                      </Tooltip>
                      {count > 1 && (
                        <>
                          <Tooltip label={t("nach vorn")}>
                            <ActionIcon
                              size="sm"
                              variant="subtle"
                              color="gray"
                              disabled={locked || page === 1}
                              onClick={() => move(page, -1)}
                              aria-label={t("Seite {{page}} nach vorn", { page })}
                            >
                              <IconArrowLeft size={14} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label={t("nach hinten")}>
                            <ActionIcon
                              size="sm"
                              variant="subtle"
                              color="gray"
                              disabled={locked || page === count}
                              onClick={() => move(page, 1)}
                              aria-label={t("Seite {{page}} nach hinten", { page })}
                            >
                              <IconArrowRight size={14} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label={t("entfernen")}>
                            <ActionIcon
                              size="sm"
                              variant="subtle"
                              color="red"
                              disabled={locked}
                              onClick={() => confirmDelete(page)}
                              aria-label={t("Seite {{page}} entfernen", { page })}
                            >
                              <IconTrash size={14} />
                            </ActionIcon>
                          </Tooltip>
                        </>
                      )}
                    </Group>
                  )}
                </Group>
              </Card>
            ))}
          </SimpleGrid>
        )}
      </Stack>
    </Paper>
  );
}

function Thumbnail({ documentId, page, version }: { documentId: string; page: number; version: string }) {
  const { t } = useTranslation();
  const blob = useQuery({
    queryKey: ["document", documentId, "thumb", version, page],
    queryFn: () => fetchPageThumbnail(documentId, page),
    staleTime: Infinity,
  });
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob.data) return;
    const objectUrl = URL.createObjectURL(blob.data);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob.data]);
  if (!url) {
    return (
      <Stack h={120} align="center" justify="center">
        {blob.isError ? (
          <Text size="xs" c="dimmed">
            {t("keine Vorschau")}
          </Text>
        ) : (
          <Loader size="xs" />
        )}
      </Stack>
    );
  }
  return <Image src={url} alt={t("Seite {{page}}", { page })} radius="xs" fit="contain" mah={220} />;
}
