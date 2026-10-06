import { Button, Stack, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <Stack align="center" py="xl">
      <Title order={2}>{t("Seite nicht gefunden")}</Title>
      <Text c="dimmed">{t("Diese Adresse gibt es in Famulus DMS nicht.")}</Text>
      <Button component={Link} to="/">
        {t("Zu den Dokumenten")}
      </Button>
    </Stack>
  );
}
