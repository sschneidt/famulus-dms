import { Button, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <Stack align="center" py="xl">
      <Title order={2}>Seite nicht gefunden</Title>
      <Text c="dimmed">Diese Adresse gibt es in HomeDMS nicht.</Text>
      <Button component={Link} to="/">
        Zu den Dokumenten
      </Button>
    </Stack>
  );
}
