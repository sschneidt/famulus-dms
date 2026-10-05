import { ActionIcon, Alert, Button, Center, Grid, Group, Loader, Menu, Stack, Tabs, Text, Title } from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { modals } from "@mantine/modals";
import { IconArrowLeft, IconDots, IconDownload, IconRefresh, IconRestore, IconTrash } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { ApiError, type DocumentDetail } from "../api/client";
import { useDeleteDocument, useDocument, useReprocessDocument, useRestoreDocument } from "../api/queries";
import { CategoryPanel } from "../components/detail/CategoryPanel";
import { HistoryPanel } from "../components/detail/HistoryPanel";
import { MetadataPanel } from "../components/detail/MetadataPanel";
import { OcrTextPanel } from "../components/detail/OcrTextPanel";
import { PagesPanel } from "../components/detail/PagesPanel";
import { PaymentPanel } from "../components/detail/PaymentPanel";
import { WiedervorlagenPanel } from "../components/detail/WiedervorlagenPanel";
import { DocumentPreview } from "../components/DocumentPreview";
import { downloadDocument } from "../lib/download";
import { formatDateTime, isProcessing } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

export function DocumentDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const isMobile = useMediaQuery("(max-width: 48em)") ?? false;
  const document = useDocument(id);

  if (document.isPending) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  if (document.isError) {
    const notFound = document.error instanceof ApiError && document.error.status === 404;
    return (
      <Stack>
        <BackButton onClick={() => navigate(-1)} />
        <Alert color={notFound ? "yellow" : "red"} title={notFound ? t("Dokument nicht gefunden") : t("Fehler")}>
          {notFound ? t("Das Dokument existiert nicht (mehr) oder Sie haben keinen Zugriff.") : document.error.message}
        </Alert>
      </Stack>
    );
  }

  const doc = document.data;
  const readOnly = Boolean(doc.deleted_at);

  const side = (
    <Stack>
      <CategoryPanel doc={doc} readOnly={readOnly} />
      <MetadataPanel doc={doc} readOnly={readOnly} />
      <PaymentPanel doc={doc} readOnly={readOnly} />
      <WiedervorlagenPanel doc={doc} readOnly={readOnly} />
    </Stack>
  );

  return (
    <Stack>
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
          <BackButton onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/"))} />
          <div style={{ minWidth: 0 }}>
            <Title order={isMobile ? 3 : 2} style={{ overflowWrap: "anywhere" }}>
              {doc.title || t("Ohne Titel")}
            </Title>
            <Text size="xs" c="dimmed">
              {t("hochgeladen {{date}}", { date: formatDateTime(doc.created_at) })}
            </Text>
          </div>
        </Group>
        <DocumentActions doc={doc} />
      </Group>

      {doc.deleted_at && <DeletedNotice doc={doc} />}

      {isMobile ? (
        <Tabs defaultValue="details" keepMounted={false}>
          <Tabs.List grow>
            <Tabs.Tab value="details">{t("Details")}</Tabs.Tab>
            <Tabs.Tab value="vorschau">{t("Vorschau")}</Tabs.Tab>
            <Tabs.Tab value="mehr">{t("Text & Verlauf")}</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="details" pt="sm">
            {side}
          </Tabs.Panel>
          <Tabs.Panel value="vorschau" pt="sm">
            <Stack>
              <DocumentPreview doc={doc} />
              <PagesPanel doc={doc} readOnly={readOnly} />
            </Stack>
          </Tabs.Panel>
          <Tabs.Panel value="mehr" pt="sm">
            <Stack>
              <OcrTextPanel doc={doc} />
              <HistoryPanel documentId={doc.id} />
            </Stack>
          </Tabs.Panel>
        </Tabs>
      ) : (
        <Grid gap="md">
          <Grid.Col span={{ base: 12, md: 7 }}>
            <Stack>
              <DocumentPreview doc={doc} />
              <PagesPanel doc={doc} readOnly={readOnly} />
              <OcrTextPanel doc={doc} />
            </Stack>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 5 }}>
            <Stack>
              {side}
              <HistoryPanel documentId={doc.id} />
            </Stack>
          </Grid.Col>
        </Grid>
      )}
    </Stack>
  );
}

function BackButton({ onClick }: { onClick(): void }) {
  const { t } = useTranslation();
  return (
    <ActionIcon variant="subtle" size="lg" onClick={onClick} aria-label={t("Zurück")}>
      <IconArrowLeft size={20} />
    </ActionIcon>
  );
}

function DocumentActions({ doc }: { doc: DocumentDetail }) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const remove = useDeleteDocument();
  const reprocess = useReprocessDocument();

  function confirmReprocess() {
    modals.openConfirmModal({
      title: t("Erneut analysieren?"),
      children: (
        <Text size="sm">
          {t(
            "Text, Kategorie und die von der KI erkannten Angaben (Betreff, Absender, Datum, Betrag, Objekt, nicht bestätigte Fristvorschläge) werden neu ermittelt – dort von Ihnen geänderte Werte gehen dabei verloren. Ein eigener Titel, eine bestätigte Kategorie, die Zahlung und bestätigte Termine bleiben erhalten. Ein Foto wird dabei zur PDF.",
          )}
        </Text>
      ),
      labels: { confirm: t("Neu analysieren"), cancel: t("Abbrechen") },
      onConfirm: () =>
        reprocess.mutate(doc.id, {
          onSuccess: () => notifySuccess(t("KI-Auswertung läuft erneut")),
          onError: (e) => notifyError(e),
        }),
    });
  }

  function confirmDelete() {
    modals.openConfirmModal({
      title: t("In den Papierkorb verschieben?"),
      children: (
        <Text size="sm">
          {t("„{{title}}“ wird in den Papierkorb verschoben und kann dort wiederhergestellt werden.", {
            title: doc.title,
          })}
        </Text>
      ),
      labels: { confirm: t("In den Papierkorb"), cancel: t("Abbrechen") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        remove.mutate(doc.id, {
          onSuccess: () => {
            notifySuccess(t("In den Papierkorb verschoben"));
            navigate("/");
          },
          onError: (e) => notifyError(e),
        }),
    });
  }

  return (
    <Group gap="xs" wrap="nowrap">
      {!doc.deleted_at && (
        <Button
          variant="default"
          leftSection={<IconRefresh size={16} />}
          visibleFrom="sm"
          disabled={isProcessing(doc)}
          loading={reprocess.isPending}
          onClick={() => confirmReprocess()}
        >
          {t("Erneut analysieren")}
        </Button>
      )}
      <Button
        variant="default"
        leftSection={<IconDownload size={16} />}
        visibleFrom="sm"
        onClick={() => downloadDocument(doc).catch((e) => notifyError(e, t("Download fehlgeschlagen")))}
      >
        {t("Herunterladen")}
      </Button>
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <ActionIcon variant="default" size="lg" aria-label={t("Weitere Aktionen")}>
            <IconDots size={18} />
          </ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item
            leftSection={<IconDownload size={14} />}
            onClick={() => downloadDocument(doc).catch((e) => notifyError(e, t("Download fehlgeschlagen")))}
          >
            {t("Herunterladen")}
          </Menu.Item>
          {!doc.deleted_at && (
            <Menu.Item
              leftSection={<IconRefresh size={14} />}
              disabled={isProcessing(doc)}
              onClick={() => confirmReprocess()}
            >
              {t("Erneut analysieren")}
            </Menu.Item>
          )}
          {!doc.deleted_at && (
            <Menu.Item leftSection={<IconTrash size={14} />} color="red" onClick={confirmDelete}>
              {t("In den Papierkorb")}
            </Menu.Item>
          )}
        </Menu.Dropdown>
      </Menu>
    </Group>
  );
}

function DeletedNotice({ doc }: { doc: DocumentDetail }) {
  const restore = useRestoreDocument();
  const { t } = useTranslation();
  return (
    <Alert color="orange" title={t("Dieses Dokument liegt im Papierkorb")}>
      <Group justify="space-between">
        <Text size="sm">
          {t("Gelöscht am {{date}}. Zum Bearbeiten erst wiederherstellen.", { date: formatDateTime(doc.deleted_at) })}
        </Text>
        <Button
          size="xs"
          leftSection={<IconRestore size={14} />}
          loading={restore.isPending}
          onClick={() =>
            restore.mutate(doc.id, {
              onSuccess: () => notifySuccess(t("Wiederhergestellt")),
              onError: (e) => notifyError(e),
            })
          }
        >
          {t("Wiederherstellen")}
        </Button>
      </Group>
    </Alert>
  );
}
