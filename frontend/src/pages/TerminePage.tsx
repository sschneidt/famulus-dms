import { Alert, Badge, Center, Group, Loader, Stack, Tabs, Text, Title } from "@mantine/core";
import dayjs from "dayjs";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import type { Wiedervorlage } from "../api/client";
import { useWiedervorlagen, type WiedervorlageStatus } from "../api/queries";
import { WiedervorlageCard } from "../components/WiedervorlageCard";
import { WiedervorlageForm } from "../components/WiedervorlageForm";
import { tk } from "../lib/format";

const TABS: { value: WiedervorlageStatus; label: string }[] = [
  { value: "offen", label: tk("Offen") },
  { value: "vorgeschlagen", label: tk("Vorschläge") },
  { value: "erledigt", label: tk("Erledigt") },
];

/** Alle Termine, Fristen und Wiedervorlagen des Haushalts. */
export function TerminePage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((x) => x.value === params.get("ansicht"))?.value ?? "offen") as WiedervorlageStatus;
  const [editing, setEditing] = useState<Wiedervorlage | null>(null);
  const proposals = useWiedervorlagen("vorgeschlagen");

  return (
    <Stack>
      <div>
        <Title order={2}>{t("Termine")}</Title>
        <Text c="dimmed" size="sm">
          {t("Fristen, Kündigungstermine und Aufbewahrungsenden aus Ihren Dokumenten.")}
        </Text>
      </div>
      <Tabs value={tab} onChange={(v) => setParams(v && v !== "offen" ? { ansicht: v } : {}, { replace: true })}>
        <Tabs.List>
          {TABS.map((x) => (
            <Tabs.Tab
              key={x.value}
              value={x.value}
              rightSection={
                x.value === "vorgeschlagen" && proposals.data?.total ? (
                  <Badge size="xs" color="orange" circle>
                    {proposals.data.total}
                  </Badge>
                ) : undefined
              }
            >
              {t(x.label)}
            </Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs>
      <TerminList status={tab} onEdit={setEditing} />
      <WiedervorlageForm
        opened={editing !== null}
        wiedervorlage={editing}
        documentId={editing?.document_id ?? ""}
        onClose={() => setEditing(null)}
      />
    </Stack>
  );
}

function TerminList({ status, onEdit }: { status: WiedervorlageStatus; onEdit(wv: Wiedervorlage): void }) {
  const { t } = useTranslation();
  const list = useWiedervorlagen(status);
  if (list.isPending) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  if (list.isError) return <Alert color="red">{list.error.message}</Alert>;

  const items = list.data.items;
  if (items.length === 0) {
    return (
      <Text c="dimmed" ta="center" py="xl">
        {status === "vorgeschlagen"
          ? t("Keine offenen Vorschläge – neue Fristen aus Dokumenten erscheinen hier zum Bestätigen.")
          : status === "offen"
            ? t("Keine offenen Termine.")
            : t("Noch nichts erledigt.")}
      </Text>
    );
  }

  if (status !== "offen") {
    const sorted =
      status === "erledigt"
        ? [...items].sort((a, b) => (b.completed_at ?? "").localeCompare(a.completed_at ?? ""))
        : items;
    return (
      <Stack gap="xs">
        {status === "vorgeschlagen" && (
          <Text size="sm" c="dimmed">
            {t("Von der KI im Dokumenttext gefunden. Erst nach dem Übernehmen wird daran erinnert.")}
          </Text>
        )}
        {sorted.map((wv) => (
          <WiedervorlageCard key={wv.id} wv={wv} onEdit={onEdit} showDocument />
        ))}
        {list.data.total > items.length && (
          <Text size="sm" c="dimmed" ta="center">
            {t("{{count}} weitere nicht angezeigt", { count: list.data.total - items.length })}
          </Text>
        )}
      </Stack>
    );
  }

  // Offene Termine nach Dringlichkeit gruppieren
  const today = dayjs().format("YYYY-MM-DD");
  const soon = dayjs().add(30, "day").format("YYYY-MM-DD");
  const groups = [
    { title: t("Fällig oder überfällig"), color: "red", items: items.filter((w) => w.due_date <= today) },
    {
      title: t("Nächste 30 Tage"),
      color: "orange",
      items: items.filter((w) => w.due_date > today && w.due_date <= soon),
    },
    { title: t("Später"), color: "gray", items: items.filter((w) => w.due_date > soon) },
  ].filter((g) => g.items.length > 0);

  return (
    <Stack gap="lg">
      {groups.map((group) => (
        <Stack key={group.title} gap="xs">
          <Group gap="xs">
            <Title order={5}>{group.title}</Title>
            <Badge size="sm" color={group.color} variant="light">
              {group.items.length}
            </Badge>
          </Group>
          {group.items.map((wv) => (
            <WiedervorlageCard key={wv.id} wv={wv} onEdit={onEdit} showDocument />
          ))}
        </Stack>
      ))}
    </Stack>
  );
}
