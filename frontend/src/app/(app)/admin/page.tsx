"use client";

import { BellRing, Save, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { logsApi, notificationsApi, settingsApi, usersApi } from "@/lib/api";
import type {
  ActivityLogEntry,
  NotificationItem,
  NotificationPolicy,
  SystemSettings,
  SystemSettingsUpdateRequest,
  UserRoleDefinition,
} from "@/types";

export default function AdminPage() {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [policy, setPolicy] = useState<NotificationPolicy | null>(null);
  const [logs, setLogs] = useState<ActivityLogEntry[]>([]);
  const [roles, setRoles] = useState<UserRoleDefinition[]>([]);
  const [alerts, setAlerts] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [savingPolicy, setSavingPolicy] = useState(false);

  const [settingsForm, setSettingsForm] = useState<SystemSettingsUpdateRequest>(
    {}
  );
  const [policyForm, setPolicyForm] = useState({
    channels: "",
    muted_repositories: "",
  });

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const [settingsRes, policyRes, logsRes, rolesRes, eventsRes] =
          await Promise.all([
            settingsApi.get(),
            notificationsApi.getPolicy(),
            logsApi.list(20),
            usersApi.listRoles(),
            notificationsApi.listEvents(),
          ]);
        setSettings(settingsRes);
        setPolicy(policyRes);
        setLogs(logsRes.logs);
        setRoles(rolesRes.roles);
        setAlerts(eventsRes.notifications);
        setSettingsForm({
          auto_rescan_enabled: settingsRes.auto_rescan_enabled,
        });
        setPolicyForm({
          channels: policyRes.channels.join(", "),
          muted_repositories: policyRes.muted_repositories.join(", "),
        });
      } catch (err) {
        console.error(err);
        setError("Unable to load admin data. Check backend API.");
      } finally {
        setLoading(false);
      }
    };

    bootstrap();
  }, []);

  const handleSettingsSubmit = async (
    event: React.FormEvent<HTMLFormElement>
  ) => {
    event.preventDefault();
    setSavingSettings(true);
    try {
      const payload: SystemSettingsUpdateRequest = {
        ...settingsForm,
        updated_by: "admin",
      };
      const updated = await settingsApi.update(payload);
      setSettings(updated);
    } catch (err) {
      console.error(err);
      setError("Unable to update system settings.");
    } finally {
      setSavingSettings(false);
    }
  };

  const handlePolicySubmit = async (
    event: React.FormEvent<HTMLFormElement>
  ) => {
    event.preventDefault();
    setSavingPolicy(true);
    try {
      const payload = {
        channels: policyForm.channels
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        muted_repositories: policyForm.muted_repositories
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        updated_by: "admin",
      };
      const updated = await notificationsApi.updatePolicy(payload);
      setPolicy(updated);
    } catch (err) {
      console.error(err);
      setError("Unable to update notification policy.");
    } finally {
      setSavingPolicy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Loading Admin Center...</CardTitle>
            <CardDescription>
              Fetching settings, logs, and alerts data.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md border-red-200 bg-red-50/60 dark:border-red-800 dark:bg-red-900/20">
          <CardHeader>
            <CardTitle className="text-red-700 dark:text-red-300">
              Không thể tải dữ liệu
            </CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Admin Control Center</CardTitle>
            <CardDescription>
              Manage model settings, policies, activity logs, and role
              permissions.
            </CardDescription>
          </div>
          <div className="text-xs text-muted-foreground">
            Last updated:{" "}
            {settings?.updated_at
              ? new Date(settings.updated_at).toLocaleString("en-US")
              : "--"}
          </div>
        </CardHeader>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>System Settings</CardTitle>
            <CardDescription>
              Adjust thresholds and automation flags (Admin only).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleSettingsSubmit}>
              <div className="grid gap-3 md:grid-cols-2">
                <ToggleField
                  label="Auto rescan"
                  checked={settingsForm.auto_rescan_enabled ?? false}
                  onChange={(checked) =>
                    setSettingsForm((prev) => ({
                      ...prev,
                      auto_rescan_enabled: checked,
                    }))
                  }
                />
              </div>
              <div className="grid gap-3 md:grid-cols-3"></div>
              <button
                type="submit"
                disabled={savingSettings}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-60"
              >
                <Save className="h-4 w-4" />
                Save settings
              </button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Notification Policy</CardTitle>
            <CardDescription>
              Configure alert thresholds & channels.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-3" onSubmit={handlePolicySubmit}>
              <FormField
                label="Channels (comma separated)"
                value={policyForm.channels}
                onChange={(value) =>
                  setPolicyForm((prev) => ({ ...prev, channels: value }))
                }
              />
              <FormField
                label="Muted repositories"
                value={policyForm.muted_repositories}
                onChange={(value) =>
                  setPolicyForm((prev) => ({
                    ...prev,
                    muted_repositories: value,
                  }))
                }
              />
              <button
                type="submit"
                disabled={savingPolicy}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
              >
                <BellRing className="h-4 w-4" />
                Save policy
              </button>
            </form>
            <p className="mt-2 text-xs text-muted-foreground">
              Last updated:{" "}
              {policy?.last_updated_at
                ? new Date(policy.last_updated_at).toLocaleString("en-US")
                : "--"}{" "}
              by {policy?.last_updated_by ?? "system"}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>Activity Logs</CardTitle>
            <CardDescription>Record recent activity logs.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {logs.map((log) => (
              <div
                key={log._id}
                className="rounded-lg border border-slate-200 bg-white/70 p-3 text-sm dark:border-slate-800 dark:bg-slate-900/70"
              >
                <p className="font-semibold text-slate-800 dark:text-slate-100">
                  {log.action}
                </p>
                <p className="text-xs text-muted-foreground">
                  {log.actor} ·{" "}
                  {new Date(log.created_at).toLocaleString("en-US")}
                </p>
                <p className="mt-1 text-sm">{log.message}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Roles & Permissions</CardTitle>
            <CardDescription>Current role definitions.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {roles.map((role) => (
              <div
                key={role.role}
                className="rounded-lg border border-slate-200 bg-white/70 p-3 dark:border-slate-800 dark:bg-slate-900/70"
              >
                <div className="flex items-center justify-between">
                  <p className="font-semibold">{role.role}</p>
                  {role.admin_only ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold uppercase text-amber-700 dark:bg-amber-900/30">
                      Admin
                    </span>
                  ) : (
                    <ShieldCheck className="h-4 w-4 text-emerald-500" />
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {role.description}
                </p>
                <ul className="mt-2 list-inside list-disc text-xs text-muted-foreground">
                  {role.permissions.map((perm) => (
                    <li key={perm}>{perm}</li>
                  ))}
                </ul>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

interface FormFieldProps {
  label: string;
  value: string;
  type?: string;
  step?: string;
  onChange: (value: string) => void;
}

function FormField({
  label,
  value,
  onChange,
  type = "text",
  step,
}: FormFieldProps) {
  return (
    <label className="text-sm">
      <span className="mb-1 block text-xs font-semibold text-muted-foreground">
        {label}
      </span>
      <input
        type={type}
        step={step}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none dark:border-slate-800 dark:bg-slate-900"
      />
    </label>
  );
}

interface ToggleFieldProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

function ToggleField({ label, checked, onChange }: ToggleFieldProps) {
  return (
    <label className="inline-flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
      />
      {label}
    </label>
  );
}
