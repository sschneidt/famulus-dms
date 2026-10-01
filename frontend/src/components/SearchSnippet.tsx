import { Mark, Text } from "@mantine/core";
import type { Schemas } from "../api/client";

/** Textausschnitt eines Suchtreffers; Treffer sind hervorgehoben (kein HTML aus dem Server). */
export function SearchSnippet({ segments }: { segments?: Schemas["SearchSegment"][] | null }) {
  if (!segments?.length) return null;
  return (
    <Text size="xs" c="dimmed" lineClamp={2} mt={2} data-testid="search-snippet">
      {segments.map((s, i) =>
        s.hit ? (
          <Mark key={i} color="yellow">
            {s.text}
          </Mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </Text>
  );
}
