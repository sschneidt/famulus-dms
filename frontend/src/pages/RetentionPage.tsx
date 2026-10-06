import {
  ActionIcon,
  Alert,
  Button,
  Card,
  Center,
  Checkbox,
  Group,
  Loader,
  Modal,
  NumberInput,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useMediaQuery } from "@mantine/hooks";
import { modals } from "@mantine/modals";
import { IconEdit, IconPlus, IconTrash } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { useDeleteRetentionRule, useRetentionRules, useSaveRetentionRule } from "../api/queries";
import { useUser } from "../auth/AuthContext";
import { useCategoryNames, useCategoryOptions } from "../lib/categories";
import { formatMonths } from "../lib/format";
import { notifyError, notifySuccess } from "../lib/notify";

type Rule = Schemas["RetentionRuleResponse"];

/**
 * Aufbewahrungsregeln (nur Admins): pro Kategorie, wie lange Dokumente aufzubewahren sind.
 * Daraus entsteht bei jedem Dokument mit Datum automatisch eine Wiedervorlage "Aufbewahrung endet".
 */
export function RetentionPage() {
  const user = useUser();
  const { t, i18n } = useTranslation();
  const isAdmin = user.role === "admin";
  const isMobile = useMediaQuery("(max-width: 48em)") ?? false;
  const rules = useRetentionRules(isAdmin);
  const remove = useDeleteRetentionRule();
  const categoryName = useCategoryNames();
  const [editing, setEditing] = useState<{ open: boolean; rule: Rule | null }>({ open: false, rule: null });

  if (!isAdmin) {
    return <Alert color="yellow">{t("Aufbewahrungsregeln können nur Administratoren verwalten.")}</Alert>;
  }

  function confirmDelete(rule: Rule) {
    modals.openConfirmModal({
      title: t("Regel löschen?"),
      children: (
        <Text size="sm">
          {t(
            "Die Regel für „{{category}}“ wird gelöscht. Offene Aufbewahrungs-Termine dieser Kategorie werden entfernt.",
            {
              category: categoryName(rule.category_id),
            },
          )}
        </Text>
      ),
      labels: { confirm: t("Löschen"), cancel: t("Abbrechen") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        remove.mutate(rule.id, {
          onSuccess: () => notifySuccess(t("Regel gelöscht")),
          onError: (e) => notifyError(e),
        }),
    });
  }

  const sorted = [...(rules.data ?? [])].sort((a, b) =>
    categoryName(a.category_id).localeCompare(categoryName(b.category_id), i18n.language),
  );

  return (
    <Stack>
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={2}>{t("Aufbewahrung")}</Title>
          <Text c="dimmed" size="sm" maw={640}>
            {t(
              "Wie lange Dokumente einer Kategorie aufbewahrt werden müssen. Famulus DMS legt daraus automatisch einen Termin an, ab dem ein Dokument entsorgt werden darf.",
            )}
          </Text>
        </div>
        <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing({ open: true, rule: null })}>
          {t("Regel")}
        </Button>
      </Group>

      {rules.isPending ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : rules.isError ? (
        <Alert color="red">{rules.error.message}</Alert>
      ) : sorted.length === 0 ? (
        <Text c="dimmed" ta="center" py="xl">
          {t("Noch keine Regeln. Übliche Werte: Steuerunterlagen 10 Jahre, Rechnungen von Handwerkern 2 Jahre.")}
        </Text>
      ) : isMobile ? (
        <Stack gap="xs">
          {sorted.map((rule) => (
            <Card key={rule.id} withBorder padding="sm" radius="md">
              <Group justify="space-between" wrap="nowrap">
                <div>
                  <Text fw={500}>{categoryName(rule.category_id)}</Text>
                  <Text size="sm" c="dimmed">
                    {rule.retention_period_months ? formatMonths(rule.retention_period_months) : "–"}
                    {rule.requires_original ? ` · ${t("Original nötig")}` : ""} ·{" "}
                    {t("Erinnerung {{count}} Tage vorher", { count: rule.notify_before_days })}
                  </Text>
                </div>
                <RowActions onEdit={() => setEditing({ open: true, rule })} onDelete={() => confirmDelete(rule)} />
              </Group>
            </Card>
          ))}
        </Stack>
      ) : (
        <Table highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("Kategorie")}</Table.Th>
              <Table.Th>{t("Aufbewahren")}</Table.Th>
              <Table.Th>{t("Papier-Original nötig")}</Table.Th>
              <Table.Th>{t("Erinnerung")}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {sorted.map((rule) => (
              <Table.Tr key={rule.id}>
                <Table.Td fw={500}>{categoryName(rule.category_id)}</Table.Td>
                <Table.Td>{rule.retention_period_months ? formatMonths(rule.retention_period_months) : "–"}</Table.Td>
                <Table.Td>{rule.requires_original ? t("ja") : t("nein")}</Table.Td>
                <Table.Td>{t("{{count}} Tage vorher", { count: rule.notify_before_days })}</Table.Td>
                <Table.Td>
                  <RowActions onEdit={() => setEditing({ open: true, rule })} onDelete={() => confirmDelete(rule)} />
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <RuleForm
        opened={editing.open}
        rule={editing.rule}
        usedCategories={(rules.data ?? []).map((r) => r.category_id).filter((id): id is string => Boolean(id))}
        onClose={() => setEditing({ open: false, rule: null })}
      />
    </Stack>
  );
}

function RowActions({ onEdit, onDelete }: { onEdit(): void; onDelete(): void }) {
  const { t } = useTranslation();
  return (
    <Group gap={4} justify="flex-end" wrap="nowrap">
      <ActionIcon variant="subtle" onClick={onEdit} aria-label={t("Bearbeiten")}>
        <IconEdit size={16} />
      </ActionIcon>
      <ActionIcon variant="subtle" color="red" onClick={onDelete} aria-label={t("Löschen")}>
        <IconTrash size={16} />
      </ActionIcon>
    </Group>
  );
}

interface RuleValues {
  category_id: string | null;
  years: number | string;
  months: number | string;
  requires_original: boolean;
  notify_before_days: number | string;
}

function RuleForm({
  opened,
  rule,
  usedCategories,
  onClose,
}: {
  opened: boolean;
  rule: Rule | null;
  usedCategories: string[];
  onClose(): void;
}) {
  const { t } = useTranslation();
  const save = useSaveRetentionRule();
  const allOptions = useCategoryOptions();
  // Pro Kategorie gibt es hoechstens eine Regel
  const options = allOptions.filter((o) => o.value === rule?.category_id || !usedCategories.includes(o.value));

  const form = useForm<RuleValues>({
    initialValues: { category_id: null, years: 10, months: 0, requires_original: false, notify_before_days: 30 },
    validate: {
      category_id: (v) => (v ? null : t("Bitte eine Kategorie wählen")),
      years: (v, values) => {
        const total = Number(v) * 12 + Number(values.months);
        return total >= 1 && total <= 1200 ? null : t("Zwischen 1 Monat und 100 Jahren");
      },
      notify_before_days: (v) => (Number(v) >= 0 && Number(v) <= 3650 ? null : t("0 bis 3650 Tage")),
    },
  });

  useEffect(() => {
    if (!opened) return;
    if (rule) {
      const total = rule.retention_period_months ?? 120;
      form.setValues({
        category_id: rule.category_id,
        years: Math.floor(total / 12),
        months: total % 12,
        requires_original: rule.requires_original,
        notify_before_days: rule.notify_before_days,
      });
    } else {
      form.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, rule]);

  const submit = form.onSubmit(async (values) => {
    try {
      await save.mutateAsync({
        id: rule?.id,
        body: {
          category_id: values.category_id!,
          retention_period_months: Number(values.years) * 12 + Number(values.months),
          requires_original: values.requires_original,
          notify_before_days: Number(values.notify_before_days),
        },
      });
      notifySuccess(t("Regel gespeichert – Termine werden angepasst"));
      onClose();
    } catch (e) {
      notifyError(e, t("Speichern fehlgeschlagen"));
    }
  });

  return (
    <Modal opened={opened} onClose={onClose} title={rule ? t("Regel bearbeiten") : t("Neue Aufbewahrungsregel")}>
      <form onSubmit={submit}>
        <Stack>
          <Select label={t("Kategorie")} data={options} searchable {...form.getInputProps("category_id")} />
          <Group grow align="flex-start">
            <NumberInput label={t("Jahre")} min={0} max={100} {...form.getInputProps("years")} />
            <NumberInput label={t("Monate")} min={0} max={11} {...form.getInputProps("months")} />
          </Group>
          <NumberInput
            label={t("Erinnerung (Tage vorher)")}
            min={0}
            max={3650}
            {...form.getInputProps("notify_before_days")}
          />
          <Checkbox
            label={t("Papier-Original muss aufbewahrt werden")}
            {...form.getInputProps("requires_original", { type: "checkbox" })}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {t("Abbrechen")}
            </Button>
            <Button type="submit" loading={save.isPending}>
              {t("Speichern")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
