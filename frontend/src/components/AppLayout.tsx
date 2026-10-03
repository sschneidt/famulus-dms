import {
  ActionIcon,
  Affix,
  AppShell,
  Avatar,
  Badge,
  Burger,
  Button,
  Group,
  Menu,
  NavLink,
  Text,
  Tooltip,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure, useMediaQuery } from "@mantine/hooks";
import {
  IconCalendarDue,
  IconCamera,
  IconCash,
  IconChecklist,
  IconFiles,
  IconFolderSearch,
  IconHome,
  IconLogout,
  IconMoon,
  IconShieldCheck,
  IconSun,
  IconTrash,
  IconUpload,
  IconUserEdit,
  IconUsers,
} from "@tabler/icons-react";
import dayjs from "dayjs";
import { useCallback, useRef, useState, type ReactNode } from "react";
import { NavLink as RouterNavLink, Outlet, useLocation } from "react-router";
import { useNeedsReview, useUnanalyzed, useUnpaid, useWiedervorlagen } from "../api/queries";
import { useAuth, useUser } from "../auth/AuthContext";
import { Logo } from "./Logo";
import { ProfileModal } from "./ProfileModal";
import { UploadContext, type UploadMode } from "./upload-context";
import { UploadModal, type PendingFile } from "./UploadModal";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  badge?: ReactNode;
  end?: boolean;
}

export function AppLayout() {
  const user = useUser();
  const { logout } = useAuth();
  const [navOpen, nav] = useDisclosure(false);
  const [profileOpen, profile] = useDisclosure(false);
  const isMobile = useMediaQuery("(max-width: 48em)") ?? false;
  const location = useLocation();
  const [upload, setUpload] = useState<{ open: boolean; files?: PendingFile[] }>({ open: false });
  const cameraInput = useRef<HTMLInputElement>(null);
  // Kamera: direkt den Aufnahme-Dialog des Handys oeffnen, das Foto landet dann im Upload-Dialog
  const openUpload = useCallback((mode: UploadMode = "files") => {
    if (mode === "camera") cameraInput.current?.click();
    else setUpload({ open: true });
  }, []);

  const review = useNeedsReview();
  const unanalyzed = useUnanalyzed();
  const proposals = useWiedervorlagen("vorgeschlagen");
  const open = useWiedervorlagen("offen");
  const today = dayjs().format("YYYY-MM-DD");
  const dueCount = open.data?.items.filter((w) => w.due_date <= today).length ?? 0;
  const unpaid = useUnpaid();
  const overdueUnpaid = unpaid.data?.items.some((d) => d.payment_due && d.payment_due < today) ?? false;

  const items: NavItem[] = [
    { to: "/", label: "Dokumente", icon: <IconFiles size={20} />, end: true },
    {
      to: "/pruefen",
      label: "Prüfen",
      icon: <IconChecklist size={20} />,
      badge: (
        <Group gap={4}>
          {review.data?.total ? (
            <Tooltip label="Kategorie prüfen">
              <Badge size="sm" color="orange" circle={review.data.total < 10}>
                {review.data.total}
              </Badge>
            </Tooltip>
          ) : null}
          {unanalyzed.data?.total ? (
            <Tooltip label="nicht analysiert">
              <Badge size="sm" color="red" variant="light" circle={unanalyzed.data.total < 10}>
                {unanalyzed.data.total}
              </Badge>
            </Tooltip>
          ) : null}
        </Group>
      ),
    },
    {
      to: "/termine",
      label: "Termine",
      icon: <IconCalendarDue size={20} />,
      badge: (
        <Group gap={4}>
          {dueCount > 0 && (
            <Tooltip label="fällig oder überfällig">
              <Badge size="sm" color="red">
                {dueCount}
              </Badge>
            </Tooltip>
          )}
          {proposals.data?.total ? (
            <Tooltip label="Vorschläge zum Bestätigen">
              <Badge size="sm" color="orange" variant="light">
                {proposals.data.total}
              </Badge>
            </Tooltip>
          ) : null}
        </Group>
      ),
    },
    {
      to: "/unbezahlt",
      label: "Unbezahlt",
      icon: <IconCash size={20} />,
      badge: unpaid.data?.total ? (
        <Badge size="sm" color={overdueUnpaid ? "red" : "orange"} variant={overdueUnpaid ? "filled" : "light"}>
          {unpaid.data.total}
        </Badge>
      ) : null,
    },
    { to: "/objekte", label: "Objekte", icon: <IconHome size={20} /> },
    { to: "/papierkorb", label: "Papierkorb", icon: <IconTrash size={20} /> },
  ];
  if (user.role === "admin") {
    items.push({ to: "/aufbewahrung", label: "Aufbewahrung", icon: <IconShieldCheck size={20} /> });
    items.push({ to: "/scan-ordner", label: "Scan-Ordner", icon: <IconFolderSearch size={20} /> });
    items.push({ to: "/benutzer", label: "Benutzer", icon: <IconUsers size={20} /> });
  }

  const isActive = (item: NavItem) =>
    item.end
      ? location.pathname === item.to || location.pathname.startsWith("/dokumente/")
      : location.pathname.startsWith(item.to);

  return (
    <UploadContext.Provider value={openUpload}>
      <AppShell
        header={{ height: 60 }}
        navbar={{ width: 240, breakpoint: "sm", collapsed: { mobile: !navOpen } }}
        padding={isMobile ? "sm" : "md"}
        // Platz fuer den Kamera-Knopf unten rechts
        styles={isMobile && location.pathname === "/" ? { main: { paddingBottom: 96 } } : undefined}
      >
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between" wrap="nowrap">
            <Group gap="sm" wrap="nowrap">
              <Burger opened={navOpen} onClick={nav.toggle} hiddenFrom="sm" size="sm" aria-label="Menü" />
              <Logo />
            </Group>
            <Group gap="xs" wrap="nowrap">
              {isMobile ? (
                <ActionIcon variant="filled" size="lg" onClick={() => openUpload("files")} aria-label="Hochladen">
                  <IconUpload size={18} />
                </ActionIcon>
              ) : (
                <Button leftSection={<IconUpload size={18} />} onClick={() => openUpload("files")}>
                  Hochladen
                </Button>
              )}
              <ColorSchemeToggle />
              <Menu position="bottom-end" withinPortal>
                <Menu.Target>
                  <ActionIcon variant="subtle" size="lg" radius="xl" aria-label="Benutzermenü">
                    <Avatar size={32} radius="xl" color="blue">
                      {initials(user.display_name || user.email)}
                    </Avatar>
                  </ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>
                    <Text size="sm" fw={500} c="var(--mantine-color-text)">
                      {user.display_name}
                    </Text>
                    <Text size="xs">{user.email}</Text>
                    <Text size="xs">
                      {user.role === "admin" ? "Administrator" : "Mitglied"}
                      {user.household_name ? ` · ${user.household_name}` : ""}
                    </Text>
                  </Menu.Label>
                  <Menu.Item leftSection={<IconUserEdit size={16} />} onClick={profile.open}>
                    Profil &amp; Haushalt
                  </Menu.Item>
                  <Menu.Divider />
                  <Menu.Item leftSection={<IconLogout size={16} />} onClick={() => void logout()}>
                    Abmelden
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Group>
          </Group>
        </AppShell.Header>

        <AppShell.Navbar p="sm">
          {items.map((item) => (
            <NavLink
              key={item.to}
              component={RouterNavLink}
              to={item.to}
              label={item.label}
              leftSection={item.icon}
              rightSection={item.badge}
              active={isActive(item)}
              onClick={nav.close}
              styles={{ root: { borderRadius: "var(--mantine-radius-md)" } }}
            />
          ))}
        </AppShell.Navbar>

        <AppShell.Main>
          <Outlet />
        </AppShell.Main>
      </AppShell>

      <ProfileModal opened={profileOpen} onClose={profile.close} />

      {isMobile && !upload.open && location.pathname === "/" && (
        <Affix position={{ bottom: 20, right: 20 }}>
          <ActionIcon
            size={56}
            radius="xl"
            variant="filled"
            onClick={() => openUpload("camera")}
            aria-label="Foto aufnehmen"
          >
            <IconCamera size={26} />
          </ActionIcon>
        </Affix>
      )}

      <input
        ref={cameraInput}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(e) => {
          const files = Array.from(e.currentTarget.files ?? []).map((file) => ({ file, source: "photo_app" as const }));
          e.currentTarget.value = "";
          if (files.length) setUpload({ open: true, files });
        }}
      />
      <UploadModal opened={upload.open} initialFiles={upload.files} onClose={() => setUpload({ open: false })} />
    </UploadContext.Provider>
  );
}

function initials(name: string): string {
  const parts = name.split(/[\s@.]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts[1]?.[0] ?? "")).toUpperCase();
}

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme("light", { getInitialValueInEffect: true });
  return (
    <ActionIcon
      variant="subtle"
      size="lg"
      onClick={() => setColorScheme(computed === "light" ? "dark" : "light")}
      aria-label="Hell/Dunkel umschalten"
    >
      {computed === "light" ? <IconMoon size={18} /> : <IconSun size={18} />}
    </ActionIcon>
  );
}
