import {
  Alert,
  Badge,
  Button,
  Card,
  Center,
  Checkbox,
  Code,
  Group,
  Loader,
  Stack,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconDownload, IconLanguage } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { useInstallOcrLanguages, useOcrLanguages, useSaveOcrLanguages } from "../api/queries";
import { useUser } from "../auth/AuthContext";
import { notifyError, notifySuccess } from "../lib/notify";

type Language = Schemas["OcrLanguage"];

/**
 * Sprachen (nur Admin): in welchen Sprachen die Texterkennung Dokumente liest. Die
 * Oberflaechensprachen der Personen sind immer dabei; fehlende Pakete laedt der Server nach.
 */
export function LanguagesPage() {
  const user = useUser();
  const { t } = useTranslation();
  const isAdmin = user.role === "admin";
  const languages = useOcrLanguages(isAdmin);

  if (!isAdmin)
    return <Alert color="yellow">{t("Die Sprachen der Texterkennung können nur Administratoren ändern.")}</Alert>;

  return (
    <Stack maw={900}>
      <div>
        <Title order={2}>{t("Sprachen")}</Title>
        <Text c="dimmed" size="sm">
          {t(
            "Die Sprache der Oberfläche wählt jede Person selbst unter „Konto & Sicherheit“. Hier legen Sie fest, in welchen Sprachen die Texterkennung Ihre Dokumente liest – die Sprachen der Oberfläche sind immer dabei.",
          )}
        </Text>
      </div>
      {languages.isPending ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : languages.isError ? (
        <Alert color="red">{languages.error.message}</Alert>
      ) : (
        <OcrLanguageForm
          key={JSON.stringify(languages.data.languages.map((l) => [l.code, l.selected]))}
          data={languages.data}
        />
      )}
    </Stack>
  );
}

function OcrLanguageForm({ data }: { data: Schemas["OcrLanguagesResponse"] }) {
  const { t } = useTranslation();
  const save = useSaveOcrLanguages();
  const install = useInstallOcrLanguages();
  const [selected, setSelected] = useState<string[]>(() => data.languages.filter((l) => l.selected).map((l) => l.code));
  const [showAll, setShowAll] = useState(false);

  const changed =
    [...selected].sort().join() !==
    data.languages
      .filter((l) => l.selected)
      .map((l) => l.code)
      .sort()
      .join();
  const prominent = data.languages.filter((l) => l.selected || l.required_by.length > 0 || l.installed);
  const others = data.languages.filter((l) => !prominent.includes(l));
  const needsDownload = data.languages.some((l) => l.status === "missing" || l.status === "failed");

  function toggle(code: string, on: boolean) {
    setSelected((s) => (on ? [...s, code] : s.filter((c) => c !== code)));
  }

  return (
    <Card withBorder radius="md" padding="lg">
      <Group gap="xs" mb={4}>
        <IconLanguage size={20} />
        <Title order={4}>{t("Texterkennung")}</Title>
      </Group>
      <Text size="sm" c="dimmed" mb="md">
        {t(
          "Wählen Sie die Sprachen, in denen Ihre Briefe und Verträge geschrieben sind. Jede zusätzliche Sprache macht die Erkennung etwas langsamer. Fehlende Sprachpakete lädt Famulus DMS automatisch herunter (einige MB, Internetzugang nötig).",
        )}
      </Text>
      <Text size="sm" mb="sm">
        {t("Verwendet:")} <Code>{data.effective}</Code>
      </Text>
      <Stack gap={6}>
        {prominent.map((l) => (
          <LanguageRow key={l.code} language={l} checked={selected.includes(l.code)} onChange={toggle} />
        ))}
        {showAll &&
          others.map((l) => (
            <LanguageRow key={l.code} language={l} checked={selected.includes(l.code)} onChange={toggle} />
          ))}
      </Stack>
      {others.length > 0 && (
        <Button
          variant="subtle"
          size="xs"
          mt="xs"
          onClick={() => setShowAll((s) => !s)}
          style={{ alignSelf: "flex-start" }}
        >
          {showAll ? t("Weniger Sprachen") : t("Weitere Sprachen ({{count}})", { count: others.length })}
        </Button>
      )}
      <Group justify="flex-end" mt="md">
        {needsDownload && (
          <Button
            variant="default"
            leftSection={<IconDownload size={16} />}
            loading={install.isPending}
            onClick={() =>
              install.mutate(undefined, {
                onSuccess: () => notifySuccess(t("Download gestartet")),
                onError: (e) => notifyError(e),
              })
            }
          >
            {t("Fehlende Pakete laden")}
          </Button>
        )}
        <Button
          disabled={!changed || selected.length === 0}
          loading={save.isPending}
          onClick={() =>
            save.mutate(selected, {
              onSuccess: () => notifySuccess(t("Gespeichert – fehlende Sprachpakete werden heruntergeladen")),
              onError: (e) => notifyError(e, t("Speichern fehlgeschlagen")),
            })
          }
        >
          {t("Speichern")}
        </Button>
      </Group>
    </Card>
  );
}

function LanguageRow({
  language: l,
  checked,
  onChange,
}: {
  language: Language;
  checked: boolean;
  onChange(code: string, on: boolean): void;
}) {
  const { t } = useTranslation();
  const required = l.required_by.length > 0;
  return (
    <Group justify="space-between" wrap="nowrap" data-testid="ocr-language">
      <Checkbox
        label={
          <span>
            {l.name}{" "}
            <Text span c="dimmed" size="xs">
              ({l.code})
            </Text>
          </span>
        }
        description={required ? t("für die Oberfläche von {{names}}", { names: l.required_by.join(", ") }) : undefined}
        checked={checked || required}
        disabled={required}
        onChange={(e) => onChange(l.code, e.currentTarget.checked)}
      />
      <StatusBadge language={l} />
    </Group>
  );
}

function StatusBadge({ language: l }: { language: Language }) {
  const { t } = useTranslation();
  if (l.status === "installed")
    return (
      <Badge color="green" variant="light">
        {t("installiert")}
      </Badge>
    );
  if (l.status === "installing")
    return (
      <Badge color="blue" variant="light" leftSection={<Loader size={10} />}>
        {t("wird geladen")}
      </Badge>
    );
  if (l.status === "failed")
    return (
      <Tooltip label={l.error ?? ""} multiline w={320}>
        <Badge color="red" variant="light">
          {t("Fehler")}
        </Badge>
      </Tooltip>
    );
  if (l.status === "missing")
    return (
      <Badge color="orange" variant="light">
        {t("fehlt")}
      </Badge>
    );
  return null;
}
