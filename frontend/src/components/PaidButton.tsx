import { Button, Group, Popover, Stack, Text, type ButtonProps } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconCash } from "@tabler/icons-react";
import dayjs from "dayjs";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { dateInputFormat } from "../i18n";

interface Props extends Omit<ButtonProps, "onClick"> {
  label?: string;
  /** vorbelegtes Datum (Standard: heute) */
  initial?: string | null;
  loading?: boolean;
  onConfirm(paidOn: string): void | Promise<void>;
}

/** "Als bezahlt markieren" mit Zahlungsdatum (vorbelegt mit heute). */
export function PaidButton({ label, initial, loading, onConfirm, ...buttonProps }: Props) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);
  const [date, setDate] = useState<string | null>(initial ?? dayjs().format("YYYY-MM-DD"));

  return (
    <Popover opened={opened} onChange={setOpened} position="bottom-start" withArrow shadow="md">
      <Popover.Target>
        <Button
          leftSection={<IconCash size={14} />}
          size="xs"
          color="green"
          variant="light"
          {...buttonProps}
          onClick={() => {
            setDate(initial ?? dayjs().format("YYYY-MM-DD"));
            setOpened((o) => !o);
          }}
        >
          {label ?? t("Als bezahlt markieren")}
        </Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="xs">
          <Text size="sm" fw={500}>
            {t("Bezahlt am")}
          </Text>
          <DateInput
            value={date}
            onChange={setDate}
            valueFormat={dateInputFormat()}
            maxDate={dayjs().format("YYYY-MM-DD")}
            aria-label={t("Zahlungsdatum")}
            popoverProps={{ withinPortal: false }}
          />
          <Group justify="flex-end" gap="xs">
            <Button size="xs" variant="default" onClick={() => setOpened(false)}>
              {t("Abbrechen")}
            </Button>
            <Button
              size="xs"
              color="green"
              disabled={!date}
              loading={loading}
              onClick={async () => {
                if (!date) return;
                await onConfirm(date);
                setOpened(false);
              }}
            >
              {t("Speichern")}
            </Button>
          </Group>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
