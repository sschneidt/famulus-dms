import {
  ActionIcon,
  Alert,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Menu,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconArrowMerge, IconDots, IconEdit, IconHome, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Property } from "../api/client";
import { useDeleteProperty, useMergeProperty, useProperties, useRenameProperty } from "../api/queries";
import { notifyError, notifySuccess } from "../lib/notify";

/**
 * Objekte (Haus/Wohnung). Entstehen automatisch aus erkannten Adressen; der Name ist zugleich der
 * Ordnername auf dem NAS (z. B. "Haus & Reparaturen/<Name>/2026/...").
 */
export function PropertiesPage() {
  const { t } = useTranslation();
  const properties = useProperties();
  const remove = useDeleteProperty();
  const [renaming, setRenaming] = useState<Property | null>(null);
  const [merging, setMerging] = useState<Property | null>(null);

  function confirmDelete(p: Property) {
    modals.openConfirmModal({
      title: t("Objekt löschen?"),
      children: (
        <Text size="sm">
          {t(
            "„{{name}}“ wird gelöscht. Die {{count}} zugehörigen Dokumente bleiben erhalten und landen im Ordner „_Ohne Adresse“.",
            { name: p.name, count: p.document_count },
          )}
        </Text>
      ),
      labels: { confirm: t("Löschen"), cancel: t("Abbrechen") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        remove.mutate(p.id, { onSuccess: () => notifySuccess(t("Objekt gelöscht")), onError: (e) => notifyError(e) }),
    });
  }

  return (
    <Stack>
      <div>
        <Title order={2}>{t("Objekte")}</Title>
        <Text c="dimmed" size="sm" maw={680}>
          {t(
            "Häuser und Wohnungen, die in Ihren Dokumenten vorkommen. Rechnungen von Handwerkern, Nebenkosten und Gebäudeversicherungen werden auf dem NAS je Objekt in einem eigenen Ordner abgelegt. Neue Adressen erkennt die KI automatisch – hier können Sie Objekte umbenennen oder doppelt erkannte zusammenführen.",
          )}
        </Text>
      </div>
      {properties.isPending ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : properties.isError ? (
        <Alert color="red">{properties.error.message}</Alert>
      ) : properties.data.length === 0 ? (
        <Card withBorder padding="xl" radius="md">
          <Stack align="center" gap="xs">
            <IconHome size={40} color="var(--mantine-color-dimmed)" />
            <Text c="dimmed" ta="center" maw={420}>
              {t(
                "Noch keine Objekte. Sobald eine Handwerker-Rechnung oder Nebenkostenabrechnung mit Adresse hochgeladen wird, erscheint das Objekt hier.",
              )}
            </Text>
          </Stack>
        </Card>
      ) : (
        <Stack gap="xs">
          {properties.data.map((p) => (
            <Card key={p.id} withBorder padding="sm" radius="md">
              <Group justify="space-between" wrap="nowrap">
                <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
                  <IconHome size={22} color="var(--mantine-color-blue-6)" style={{ flexShrink: 0 }} />
                  <div style={{ minWidth: 0 }}>
                    <Text fw={500} style={{ overflowWrap: "anywhere" }}>
                      {p.name}
                    </Text>
                    <Text size="sm" c="dimmed">
                      {p.street}, {p.postal_code} {p.city} · {t("{{count}} Dokumente", { count: p.document_count })}
                    </Text>
                  </div>
                </Group>
                <Group gap="xs" wrap="nowrap" style={{ flexShrink: 0 }}>
                  <Menu position="bottom-end" withinPortal>
                    <Menu.Target>
                      <ActionIcon
                        variant="subtle"
                        color="gray"
                        aria-label={t("Aktionen für {{name}}", { name: p.name })}
                      >
                        <IconDots size={16} />
                      </ActionIcon>
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item leftSection={<IconEdit size={14} />} onClick={() => setRenaming(p)}>
                        {t("Umbenennen")}
                      </Menu.Item>
                      <Menu.Item
                        leftSection={<IconArrowMerge size={14} />}
                        disabled={properties.data.length < 2}
                        onClick={() => setMerging(p)}
                      >
                        {t("Mit anderem Objekt zusammenführen")}
                      </Menu.Item>
                      <Menu.Item leftSection={<IconTrash size={14} />} color="red" onClick={() => confirmDelete(p)}>
                        {t("Löschen")}
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>
                </Group>
              </Group>
            </Card>
          ))}
        </Stack>
      )}
      <RenameModal property={renaming} onClose={() => setRenaming(null)} />
      <MergeModal property={merging} all={properties.data ?? []} onClose={() => setMerging(null)} />
    </Stack>
  );
}

function RenameModal({ property, onClose }: { property: Property | null; onClose(): void }) {
  const { t } = useTranslation();
  const rename = useRenameProperty();
  const [name, setName] = useState("");
  const [lastId, setLastId] = useState<string | null>(null);
  if (property && property.id !== lastId) {
    setLastId(property.id);
    setName(property.name);
  }

  async function save() {
    if (!property || !name.trim()) return;
    try {
      await rename.mutateAsync({ id: property.id, name: name.trim() });
      notifySuccess(t("Umbenannt – der Ordner auf dem NAS wird angepasst"));
      onClose();
    } catch (e) {
      notifyError(e, t("Umbenennen fehlgeschlagen"));
    }
  }

  return (
    <Modal opened={property !== null} onClose={onClose} title={t("Objekt umbenennen")}>
      <Stack>
        <TextInput
          label={t("Name (= Ordnername)")}
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          onKeyDown={(e) => e.key === "Enter" && void save()}
          data-autofocus
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t("Abbrechen")}
          </Button>
          <Button onClick={() => void save()} loading={rename.isPending} disabled={!name.trim()}>
            {t("Speichern")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function MergeModal({ property, all, onClose }: { property: Property | null; all: Property[]; onClose(): void }) {
  const { t } = useTranslation();
  const merge = useMergeProperty();
  const [target, setTarget] = useState<string | null>(null);
  const options = all.filter((p) => p.id !== property?.id).map((p) => ({ value: p.id, label: p.name }));

  async function save() {
    if (!property || !target) return;
    try {
      await merge.mutateAsync({ id: property.id, intoId: target });
      notifySuccess(t("Zusammengeführt"));
      setTarget(null);
      onClose();
    } catch (e) {
      notifyError(e, t("Zusammenführen fehlgeschlagen"));
    }
  }

  return (
    <Modal opened={property !== null} onClose={onClose} title={t("Objekte zusammenführen")}>
      <Stack>
        <Text size="sm">
          {t("Alle Dokumente von „{{name}}“ werden dem gewählten Objekt zugeordnet; „{{name}}“ wird danach gelöscht.", {
            name: property?.name ?? "",
          })}
        </Text>
        <Select label={t("Zusammenführen mit")} data={options} value={target} onChange={setTarget} searchable />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t("Abbrechen")}
          </Button>
          <Button onClick={() => void save()} loading={merge.isPending} disabled={!target}>
            {t("Zusammenführen")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
