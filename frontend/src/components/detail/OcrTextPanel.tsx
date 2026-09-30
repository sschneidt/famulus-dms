import { Accordion, Badge, CopyButton, Button, Group, ScrollArea, Text } from "@mantine/core";
import type { DocumentDetail } from "../../api/client";

export function OcrTextPanel({ doc }: { doc: DocumentDetail }) {
  const text = doc.ocr_text?.trim();
  return (
    <Accordion variant="separated" radius="md">
      <Accordion.Item value="text">
        <Accordion.Control>
          <Group gap="xs">
            <Text fw={500}>Erkannter Text</Text>
            {doc.ocr_status === "pending" && (
              <Badge variant="light" color="gray">
                läuft
              </Badge>
            )}
            {doc.ocr_status === "failed" && (
              <Badge variant="light" color="red">
                fehlgeschlagen
              </Badge>
            )}
            {text && (
              <Text size="xs" c="dimmed">
                {text.length.toLocaleString("de-DE")} Zeichen
              </Text>
            )}
          </Group>
        </Accordion.Control>
        <Accordion.Panel>
          {text ? (
            <>
              <Group justify="flex-end" mb="xs">
                <CopyButton value={text}>
                  {({ copied, copy }) => (
                    <Button size="xs" variant="light" color={copied ? "green" : undefined} onClick={copy}>
                      {copied ? "Kopiert" : "Text kopieren"}
                    </Button>
                  )}
                </CopyButton>
              </Group>
              <ScrollArea.Autosize mah={400}>
                <Text size="sm" style={{ whiteSpace: "pre-wrap", fontFamily: "var(--mantine-font-family-monospace)" }}>
                  {text}
                </Text>
              </ScrollArea.Autosize>
            </>
          ) : (
            <Text size="sm" c="dimmed">
              Kein Text erkannt.
            </Text>
          )}
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
