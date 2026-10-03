import { Button, Divider, Group, Modal, PasswordInput, Stack, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { api, call } from "../api/client";
import { useAuth, useUser } from "../auth/AuthContext";
import { notifyError, notifySuccess } from "../lib/notify";

/**
 * Eigenen Anzeigenamen und (als Admin) den Haushaltsnamen aendern. Praxisfall: Beim Einrichten
 * ueber die API-Doku (/docs) blieb der Beispielwert "string" als Name stehen.
 */
export function ProfileModal({ opened, onClose }: { opened: boolean; onClose(): void }) {
  return (
    <Modal opened={opened} onClose={onClose} title="Profil & Haushalt">
      {opened && <ProfileForm onClose={onClose} />}
    </Modal>
  );
}

function ProfileForm({ onClose }: { onClose(): void }) {
  const user = useUser();
  const { refresh } = useAuth();
  const isAdmin = user.role === "admin";
  const [displayName, setDisplayName] = useState(user.display_name);
  const [household, setHousehold] = useState(user.household_name ?? "");
  const [saving, setSaving] = useState(false);

  const nameChanged = displayName.trim() !== user.display_name;
  const householdChanged = isAdmin && household.trim() !== (user.household_name ?? "");
  const valid = displayName.trim() !== "" && (!isAdmin || household.trim() !== "");

  async function save() {
    setSaving(true);
    try {
      if (nameChanged) {
        await call(api.PATCH("/api/v1/auth/me", { body: { display_name: displayName.trim() } }));
      }
      if (householdChanged) {
        const result = await call(api.PATCH("/api/v1/tenant", { body: { name: household.trim() } }));
        if (result.documents_refiled) {
          notifySuccess(`Haushalt umbenannt – ${result.documents_refiled} Dokument(e) ziehen in den neuen Ordner um.`);
        }
      }
      await refresh();
      if (nameChanged && !householdChanged) notifySuccess("Name gespeichert");
      onClose();
    } catch (e) {
      notifyError(e, "Speichern fehlgeschlagen");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack>
      <TextInput
        label="Dein Name"
        description="Wird oben rechts und bei deinen Dokumenten angezeigt"
        value={displayName}
        onChange={(e) => setDisplayName(e.currentTarget.value)}
        error={displayName.trim() === "" ? "Bitte einen Namen angeben" : undefined}
        data-autofocus
      />
      <TextInput label="E-Mail" value={user.email} disabled />
      {isAdmin && (
        <TextInput
          label="Name des Haushalts"
          description="Zugleich der oberste Ordner in der Ablage – beim Ändern werden die Dateien verschoben"
          value={household}
          onChange={(e) => setHousehold(e.currentTarget.value)}
          error={household.trim() === "" ? "Bitte einen Namen angeben" : undefined}
        />
      )}
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose} disabled={saving}>
          Abbrechen
        </Button>
        <Button onClick={() => void save()} loading={saving} disabled={!valid || (!nameChanged && !householdChanged)}>
          Speichern
        </Button>
      </Group>
      <Divider />
      <PasswordForm email={user.email} />
    </Stack>
  );
}

/** Eigenes Passwort aendern. Der Server meldet dabei alle Geraete ab - dieses meldet sich gleich neu an. */
function PasswordForm({ email }: { email: string }) {
  const { login } = useAuth();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [saving, setSaving] = useState(false);

  if (!open) {
    return (
      <Group justify="space-between">
        <Text size="sm">Passwort</Text>
        <Button variant="light" size="xs" onClick={() => setOpen(true)}>
          Passwort ändern
        </Button>
      </Group>
    );
  }
  const mismatch = repeat !== "" && repeat !== next;
  const valid = current !== "" && next.length >= 8 && next === repeat;

  async function change() {
    setSaving(true);
    try {
      await call(api.PUT("/api/v1/auth/password", { body: { current_password: current, new_password: next } }));
      await login(email, next); // alte Anmeldungen sind jetzt ungueltig
      notifySuccess("Passwort geändert – andere Geräte sind abgemeldet");
      setOpen(false);
      setCurrent("");
      setNext("");
      setRepeat("");
    } catch (e) {
      notifyError(e, "Passwort nicht geändert");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack gap="xs">
      <Text size="sm" fw={500}>
        Passwort ändern
      </Text>
      <PasswordInput label="Bisheriges Passwort" value={current} onChange={(e) => setCurrent(e.currentTarget.value)} />
      <PasswordInput
        label="Neues Passwort"
        description="Mindestens 8 Zeichen"
        value={next}
        onChange={(e) => setNext(e.currentTarget.value)}
        error={next.length > 0 && next.length < 8 ? "Mindestens 8 Zeichen" : undefined}
      />
      <PasswordInput
        label="Neues Passwort wiederholen"
        value={repeat}
        onChange={(e) => setRepeat(e.currentTarget.value)}
        error={mismatch ? "Stimmt nicht überein" : undefined}
      />
      <Group justify="flex-end">
        <Button variant="default" size="xs" onClick={() => setOpen(false)} disabled={saving}>
          Abbrechen
        </Button>
        <Button size="xs" onClick={() => void change()} loading={saving} disabled={!valid}>
          Passwort ändern
        </Button>
      </Group>
    </Stack>
  );
}
