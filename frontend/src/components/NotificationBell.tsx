import { ActionIcon, Button, Group, Indicator, Popover, ScrollArea, Stack, Text, UnstyledButton } from "@mantine/core";
import { IconBell, IconCalendarDue, IconChecklist, IconFiles, IconSparkles } from "@tabler/icons-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import type { Schemas } from "../api/client";
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications } from "../api/queries";
import { formatDateTime } from "../lib/format";

type Item = Schemas["NotificationItem"];

const ICONS: Record<string, ReactNode> = {
  wiedervorlage_due: <IconCalendarDue size={18} />,
  wiedervorlage_vorschlag: <IconSparkles size={18} />,
  needs_review: <IconChecklist size={18} />,
  new_document: <IconFiles size={18} />,
};

/** Glocke oben rechts: Benachrichtigungscenter mit den Eintraegen der taeglichen Zusammenfassung. */
export function NotificationBell() {
  const [opened, setOpened] = useState(false);
  const { t } = useTranslation();
  const list = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();
  const navigate = useNavigate();
  const unread = list.data?.unread ?? 0;

  function open(item: Item) {
    if (!item.read) markRead.mutate(item.id);
    setOpened(false);
    void navigate(item.url);
  }

  return (
    <Popover
      opened={opened}
      onChange={setOpened}
      position="bottom-end"
      width={360}
      shadow="md"
      withinPortal
      hideDetached={false}
    >
      <Popover.Target>
        <ActionIcon
          variant="subtle"
          size="lg"
          onClick={() => setOpened((o) => !o)}
          aria-label={
            unread ? t("Benachrichtigungen ({{count}} ungelesen)", { count: unread }) : t("Benachrichtigungen")
          }
        >
          <Indicator label={unread > 9 ? "9+" : unread} size={16} color="red" disabled={!unread} offset={2}>
            <IconBell size={18} style={{ display: "block" }} />
          </Indicator>
        </ActionIcon>
      </Popover.Target>
      <Popover.Dropdown p={0}>
        <Group
          justify="space-between"
          px="md"
          py="xs"
          style={{ borderBottom: "1px solid var(--mantine-color-default-border)" }}
        >
          <Text fw={600} size="sm">
            {t("Benachrichtigungen")}
          </Text>
          {unread > 0 && (
            <Button size="compact-xs" variant="subtle" onClick={() => markAll.mutate()} loading={markAll.isPending}>
              {t("Alle gelesen")}
            </Button>
          )}
        </Group>
        <ScrollArea.Autosize mah={420}>
          {list.data?.items.length ? (
            <Stack gap={0}>
              {list.data.items.map((item) => (
                <UnstyledButton
                  key={item.id}
                  onClick={() => open(item)}
                  px="md"
                  py="sm"
                  data-testid="notification"
                  style={{
                    borderBottom: "1px solid var(--mantine-color-default-border)",
                    background: item.read ? undefined : "var(--mantine-color-blue-light)",
                  }}
                >
                  <Group gap="sm" wrap="nowrap" align="flex-start">
                    <Text c={item.type === "wiedervorlage_due" ? "red" : "blue"} mt={2}>
                      {ICONS[item.type] ?? <IconBell size={18} />}
                    </Text>
                    <div style={{ minWidth: 0 }}>
                      <Text size="sm" fw={item.read ? 400 : 600}>
                        {item.title}
                      </Text>
                      <Text size="sm" c="dimmed">
                        {item.body}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {formatDateTime(item.created_at)}
                      </Text>
                    </div>
                  </Group>
                </UnstyledButton>
              ))}
            </Stack>
          ) : (
            <Text size="sm" c="dimmed" p="md">
              {list.isPending
                ? t("Wird geladen …")
                : t("Keine Benachrichtigungen. Fällige Termine erscheinen hier einmal täglich.")}
            </Text>
          )}
        </ScrollArea.Autosize>
        <Group justify="flex-end" px="md" py={6} style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
          <Button
            size="compact-xs"
            variant="subtle"
            onClick={() => {
              setOpened(false);
              void navigate("/konto#benachrichtigungen");
            }}
          >
            {t("Einstellungen")}
          </Button>
        </Group>
      </Popover.Dropdown>
    </Popover>
  );
}
