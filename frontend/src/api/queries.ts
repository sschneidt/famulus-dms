/**
 * Alle Datenabfragen und Aenderungen an einer Stelle (TanStack Query). Nach jeder Aenderung
 * werden die betroffenen Abfragen neu geladen, damit alle Ansichten aktuell bleiben.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, call, isProcessingAny, type Schemas } from "./queries-support";

export const keys = {
  categories: ["categories"] as const,
  documents: (filters: object) => ["documents", filters] as const,
  document: (id: string) => ["document", id] as const,
  history: (id: string) => ["document", id, "history"] as const,
  documentWiedervorlagen: (id: string) => ["document", id, "wiedervorlagen"] as const,
  needsReview: ["documents", "needs-review"] as const,
  trash: ["documents", "trash"] as const,
  wiedervorlagen: (filters: object) => ["wiedervorlagen", filters] as const,
  retentionRules: ["retention-rules"] as const,
  properties: ["properties"] as const,
};

export interface DocumentFilters {
  page: number;
  page_size: number;
  category_id?: string;
  status?: "pending" | "auto_assigned" | "needs_review" | "confirmed";
  q?: string;
}

// --- Lesen ---------------------------------------------------------------------------------

export function useCategories() {
  return useQuery({
    queryKey: keys.categories,
    queryFn: () => call(api.GET("/api/v1/categories")),
    staleTime: 60_000,
  });
}

export function useDocuments(filters: DocumentFilters) {
  return useQuery({
    queryKey: keys.documents(filters),
    queryFn: () => call(api.GET("/api/v1/documents", { params: { query: filters } })),
    // solange Dokumente noch verarbeitet werden, regelmaessig nachsehen
    refetchInterval: (q) => (q.state.data && isProcessingAny(q.state.data.items) ? 3000 : false),
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: keys.document(id),
    queryFn: () => call(api.GET("/api/v1/documents/{document_id}", { params: { path: { document_id: id } } })),
    refetchInterval: (q) => (q.state.data && isProcessingAny([q.state.data]) ? 3000 : false),
  });
}

export function useClassificationHistory(id: string) {
  return useQuery({
    queryKey: keys.history(id),
    queryFn: () =>
      call(
        api.GET("/api/v1/documents/{document_id}/classification-history", { params: { path: { document_id: id } } }),
      ),
  });
}

export function useDocumentWiedervorlagen(id: string, processing = false) {
  return useQuery({
    queryKey: keys.documentWiedervorlagen(id),
    queryFn: () =>
      call(api.GET("/api/v1/documents/{document_id}/wiedervorlagen", { params: { path: { document_id: id } } })),
    refetchInterval: processing ? 3000 : false,
  });
}

export function useNeedsReview() {
  return useQuery({
    queryKey: keys.needsReview,
    queryFn: () => call(api.GET("/api/v1/documents/needs-review", { params: { query: { page_size: 100 } } })),
    refetchInterval: 30_000,
  });
}

export function useTrash() {
  return useQuery({
    queryKey: keys.trash,
    queryFn: () => call(api.GET("/api/v1/documents/trash", { params: { query: { page_size: 100 } } })),
  });
}

export type WiedervorlageStatus = "vorgeschlagen" | "offen" | "erledigt" | "verworfen";

export function useWiedervorlagen(status: WiedervorlageStatus, pageSize = 100) {
  return useQuery({
    queryKey: keys.wiedervorlagen({ status, pageSize }),
    queryFn: () => call(api.GET("/api/v1/wiedervorlagen", { params: { query: { status, page_size: pageSize } } })),
    refetchInterval: 30_000,
  });
}

export function useRetentionRules(enabled: boolean) {
  return useQuery({
    queryKey: keys.retentionRules,
    queryFn: () => call(api.GET("/api/v1/retention-rules")),
    enabled,
  });
}

export function useProperties() {
  return useQuery({
    queryKey: keys.properties,
    queryFn: () => call(api.GET("/api/v1/properties")),
    staleTime: 30_000,
  });
}

// --- Aendern -------------------------------------------------------------------------------

function useInvalidateAll() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["documents"] }),
      qc.invalidateQueries({ queryKey: ["document"] }),
      qc.invalidateQueries({ queryKey: ["wiedervorlagen"] }),
      qc.invalidateQueries({ queryKey: ["properties"] }),
    ]);
}

export function useUpdateDocument(id: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: Schemas["DocumentUpdateRequest"]) =>
      call(api.PATCH("/api/v1/documents/{document_id}", { params: { path: { document_id: id } }, body })),
    onSuccess: invalidate,
  });
}

export function useAssignCategory() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ documentId, categoryId }: { documentId: string; categoryId: string }) =>
      call(
        api.POST("/api/v1/documents/{document_id}/category", {
          params: { path: { document_id: documentId } },
          body: { category_id: categoryId },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useDeleteDocument() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) =>
      call(api.DELETE("/api/v1/documents/{document_id}", { params: { path: { document_id: id } } })),
    onSuccess: invalidate,
  });
}

export function useRestoreDocument() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) =>
      call(api.POST("/api/v1/documents/{document_id}/restore", { params: { path: { document_id: id } } })),
    onSuccess: invalidate,
  });
}

type WvAction = "confirm" | "reject" | "complete";
export function useWiedervorlageAction() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({
      id,
      action,
    }: {
      id: string;
      action: WvAction;
    }): Promise<Schemas["WiedervorlageResponse"] | Schemas["WiedervorlageCompleteResponse"]> => {
      const params = { params: { path: { wiedervorlage_id: id } } };
      if (action === "confirm") return call(api.POST("/api/v1/wiedervorlagen/{wiedervorlage_id}/confirm", params));
      if (action === "reject") return call(api.POST("/api/v1/wiedervorlagen/{wiedervorlage_id}/reject", params));
      return call(api.POST("/api/v1/wiedervorlagen/{wiedervorlage_id}/complete", params));
    },
    onSuccess: invalidate,
  });
}

export function useCreateWiedervorlage(documentId: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: Schemas["WiedervorlageCreate"]) =>
      call(
        api.POST("/api/v1/documents/{document_id}/wiedervorlagen", {
          params: { path: { document_id: documentId } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useUpdateWiedervorlage() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Schemas["WiedervorlageUpdate"] }) =>
      call(
        api.PATCH("/api/v1/wiedervorlagen/{wiedervorlage_id}", { params: { path: { wiedervorlage_id: id } }, body }),
      ),
    onSuccess: invalidate,
  });
}

export function useDeleteWiedervorlage() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) =>
      call(api.DELETE("/api/v1/wiedervorlagen/{wiedervorlage_id}", { params: { path: { wiedervorlage_id: id } } })),
    onSuccess: invalidate,
  });
}

export function useSaveRetentionRule() {
  const qc = useQueryClient();
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: Schemas["RetentionRuleCreate"] }) =>
      id
        ? call(api.PATCH("/api/v1/retention-rules/{rule_id}", { params: { path: { rule_id: id } }, body }))
        : call(api.POST("/api/v1/retention-rules", { body })),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: keys.retentionRules }), invalidate()]),
  });
}

export function useDeleteRetentionRule() {
  const qc = useQueryClient();
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) =>
      call(api.DELETE("/api/v1/retention-rules/{rule_id}", { params: { path: { rule_id: id } } })),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: keys.retentionRules }), invalidate()]),
  });
}

export function useReprocessDocument() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) =>
      call(api.POST("/api/v1/documents/{document_id}/reprocess", { params: { path: { document_id: id } } })),
    onSuccess: invalidate,
  });
}

function usePropertyMutation<T>(fn: (vars: T) => Promise<unknown>) {
  const qc = useQueryClient();
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: keys.properties }), invalidate()]),
  });
}

export function useRenameProperty() {
  return usePropertyMutation(({ id, name }: { id: string; name: string }) =>
    call(api.PATCH("/api/v1/properties/{property_id}", { params: { path: { property_id: id } }, body: { name } })),
  );
}

export function useMergeProperty() {
  return usePropertyMutation(({ id, intoId }: { id: string; intoId: string }) =>
    call(
      api.POST("/api/v1/properties/{property_id}/merge", {
        params: { path: { property_id: id } },
        body: { into_id: intoId },
      }),
    ),
  );
}

export function useDeleteProperty() {
  return usePropertyMutation((id: string) =>
    call(api.DELETE("/api/v1/properties/{property_id}", { params: { path: { property_id: id } } })),
  );
}
