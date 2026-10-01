import type { RouteObject } from "react-router";
import { AppLayout } from "./components/AppLayout";
import { RequireAuth } from "./components/RequireAuth";
import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PropertiesPage } from "./pages/PropertiesPage";
import { RetentionPage } from "./pages/RetentionPage";
import { ReviewPage } from "./pages/ReviewPage";
import { TerminePage } from "./pages/TerminePage";
import { TrashPage } from "./pages/TrashPage";

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <DocumentsPage /> },
      { path: "dokumente/:id", element: <DocumentDetailPage /> },
      { path: "pruefen", element: <ReviewPage /> },
      { path: "termine", element: <TerminePage /> },
      { path: "objekte", element: <PropertiesPage /> },
      { path: "papierkorb", element: <TrashPage /> },
      { path: "aufbewahrung", element: <RetentionPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
