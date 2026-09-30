import { Alert, Badge, Center, Group, Loader, Stack, Tabs, Text, Title } from "@mantine/core";
import dayjs from "dayjs";
import { useState } from "react";
import { useSearchParams } from "react-router";
import type { Wiedervorlage } from "../api/client";
import { useWiedervorlagen, type WiedervorlageStatus } from "../api/queries";
import { WiedervorlageCard } from "../components/WiedervorlageCard";
import { WiedervorlageForm } from "../components/WiedervorlageForm";

const TABS: { value: WiedervorlageStatus; label: string }[] = [
  { value: "offen", label: "Offen" },
  { value: "vorgeschlagen", label: "Vorschläge" },
  { value: "erledigt", label: "Erledigt" },
];

/** Alle Termine, Fristen und Wiedervorlagen des Haushalts. */
export function TerminePage() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.value === params.get("ansicht"))?.value ?? "offen") as WiedervorlageStatus;
  const [editing, setEditing] = useState<Wiedervorlage | null>(null);
  const proposals = useWiedervorlagen("vorgeschlagen");

  return (
    <Stack>
      <div>
        <Title order={2}>Termine</Title>
        <Text c="dimmed" size="sm">
          Fristen, Kündigungstermine und Aufbewahrungsenden aus Ihren Dokumenten.
        </Text>
      </div>
      <Tabs value={tab} onChange={(v) => setParams(v && v !== "offen" ? { ansicht: v } : {}, { replace: true })}>
        <Tabs.List>
          {TABS.map((t) => (
            <Tabs.Tab
              key={t.value}
              value={t.value}
              rightSection={
                t.value === "vorgeschlagen" && proposals.data?.total ? (
                  <Badge size="xs" color="orange" circle>
                    {proposals.data.total}
                  </Badge>
                ) : undefined
              }
            >
              {t.label}
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
          ? "Keine offenen Vorschläge – neue Fristen aus Dokumenten erscheinen hier zum Bestätigen."
          : status === "offen"
            ? "Keine offenen Termine."
            : "Noch nichts erledigt."}
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
            Von der KI im Dokumenttext gefunden. Erst nach dem Übernehmen wird daran erinnert.
          </Text>
        )}
        {sorted.map((wv) => (
          <WiedervorlageCard key={wv.id} wv={wv} onEdit={onEdit} showDocument />
        ))}
        {list.data.total > items.length && (
          <Text size="sm" c="dimmed" ta="center">
            {list.data.total - items.length} weitere nicht angezeigt
          </Text>
        )}
      </Stack>
    );
  }

  // Offene Termine nach Dringlichkeit gruppieren
  const today = dayjs().format("YYYY-MM-DD");
  const soon = dayjs().add(30, "day").format("YYYY-MM-DD");
  const groups = [
    { title: "Fällig oder überfällig", color: "red", items: items.filter((w) => w.due_date <= today) },
    { title: "Nächste 30 Tage", color: "orange", items: items.filter((w) => w.due_date > today && w.due_date <= soon) },
    { title: "Später", color: "gray", items: items.filter((w) => w.due_date > soon) },
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
