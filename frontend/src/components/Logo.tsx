import { Group, Text, ThemeIcon } from "@mantine/core";
import { IconFileText } from "@tabler/icons-react";

export function Logo({ size = "lg" }: { size?: "md" | "lg" | "xl" }) {
  return (
    <Group gap={8} wrap="nowrap">
      <ThemeIcon size={size} radius="md" variant="filled">
        <IconFileText size={18} />
      </ThemeIcon>
      <Text fw={700} size={size}>
        HomeDMS
      </Text>
    </Group>
  );
}
