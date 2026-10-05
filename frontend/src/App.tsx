import { MantineProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { createBrowserRouter, RouterProvider } from "react-router";
import { AuthProvider } from "./auth/AuthContext";
import { dayjsLocale, initLanguage } from "./i18n";
import { createQueryClient } from "./lib/queryClient";
import { routes } from "./routes";
import { theme } from "./theme";

initLanguage();

export function App() {
  const [queryClient] = useState(createQueryClient);
  const [router] = useState(() => createBrowserRouter(routes));
  const { t, i18n } = useTranslation();
  // Sprache gewechselt: Texte vom Server (Meldungen, Diagnose, Glocke) neu holen
  useEffect(() => {
    const reload = () => void queryClient.invalidateQueries();
    i18n.on("languageChanged", reload);
    return () => i18n.off("languageChanged", reload);
  }, [i18n, queryClient]);
  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <DatesProvider settings={{ locale: dayjsLocale(), firstDayOfWeek: 1 }}>
        <QueryClientProvider client={queryClient}>
          <ModalsProvider labels={{ confirm: t("OK"), cancel: t("Abbrechen") }}>
            <Notifications position="top-right" />
            <AuthProvider>
              <RouterProvider router={router} />
            </AuthProvider>
          </ModalsProvider>
        </QueryClientProvider>
      </DatesProvider>
    </MantineProvider>
  );
}
