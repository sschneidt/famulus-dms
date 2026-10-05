import { Alert, Anchor, Button, Card, Center, Group, Loader, Stack, Text, Title } from "@mantine/core";
import { IconRestore, IconTrash } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { useRestoreDocument, useTrash } from "../api/queries";
import { useCategoryNames } from "../lib/categories";
import { formatDateTime } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

export function TrashPage() {
  const { t } = useTranslation();
  const trash = useTrash();
  const restore = useRestoreDocument();
  const categoryName = useCategoryNames();

  return (
    <Stack>
      <div>
        <Title order={2}>{t("Papierkorb")}</Title>
        <Text c="dimmed" size="sm">
          {t("Gelöschte Dokumente lassen sich hier wiederherstellen.")}
        </Text>
      </div>
      {trash.isPending ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : trash.isError ? (
        <Alert color="red">{trash.error.message}</Alert>
      ) : trash.data.items.length === 0 ? (
        <Card withBorder padding="xl" radius="md">
          <Stack align="center" gap="xs">
            <IconTrash size={40} color="var(--mantine-color-dimmed)" />
            <Text c="dimmed">{t("Der Papierkorb ist leer.")}</Text>
          </Stack>
        </Card>
      ) : (
        <Stack gap="xs">
          {trash.data.items.map((doc) => (
            <Card key={doc.id} withBorder padding="sm" radius="md">
              <Group justify="space-between" wrap="nowrap">
                <div style={{ minWidth: 0 }}>
                  <Anchor component={Link} to={`/dokumente/${doc.id}`} fw={500} style={{ overflowWrap: "anywhere" }}>
                    {doc.title || t("Ohne Titel")}
                  </Anchor>
                  <Text size="xs" c="dimmed">
                    {categoryName(doc.category_id)} · {t("gelöscht {{date}}", { date: formatDateTime(doc.deleted_at) })}
                  </Text>
                </div>
                <Button
                  size="xs"
                  variant="light"
                  leftSection={<IconRestore size={14} />}
                  loading={restore.isPending && restore.variables === doc.id}
                  onClick={() =>
                    restore.mutate(doc.id, {
                      onSuccess: () => notifySuccess(t("„{{title}}“ wiederhergestellt", { title: doc.title })),
                      onError: (e) => notifyError(e),
                    })
                  }
                  style={{ flexShrink: 0 }}
                >
                  {t("Wiederherstellen")}
                </Button>
              </Group>
            </Card>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
