'use client';

import { useState, useEffect } from 'react';
import { Bell, Check, Loader2, Save, User } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuth } from '@/contexts/auth-context';
import { useToast } from '@/components/ui/use-toast';

interface NotificationPreferences {
    emailOnVersionComplete: boolean;
    emailOnScanComplete: boolean;
    emailOnVersionFailed: boolean;
    browserNotifications: boolean;
}

interface UserSettingsState {
    notificationPreferences: NotificationPreferences;
    isLoading: boolean;
    isSaving: boolean;
    hasChanges: boolean;
}

const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
    emailOnVersionComplete: true,
    emailOnScanComplete: true,
    emailOnVersionFailed: true,
    browserNotifications: true,
};

export default function SettingsPage() {
    const { user } = useAuth();
    const { toast } = useToast();

    const [settingsState, setSettingsState] = useState<UserSettingsState>({
        notificationPreferences: DEFAULT_NOTIFICATION_PREFERENCES,
        isLoading: true,
        isSaving: false,
        hasChanges: false,
    });

    // Load user settings on mount
    useEffect(() => {
        const loadSettings = async () => {
            // TODO: Fetch from API when backend endpoint is ready
            // For now, use defaults
            setSettingsState(prev => ({
                ...prev,
                isLoading: false,
            }));
        };

        loadSettings();
    }, []);

    const updateNotificationPreference = (
        preferenceKey: keyof NotificationPreferences,
        enabled: boolean
    ) => {
        setSettingsState(prev => ({
            ...prev,
            notificationPreferences: {
                ...prev.notificationPreferences,
                [preferenceKey]: enabled,
            },
            hasChanges: true,
        }));
    };

    const handleSaveSettings = async () => {
        setSettingsState(prev => ({ ...prev, isSaving: true }));

        try {
            // TODO: Call API to save settings when backend endpoint is ready
            // await api.updateUserSettings(settingsState.notificationPreferences);

            // Simulate API call
            await new Promise(resolve => setTimeout(resolve, 500));

            toast({
                title: 'Settings saved',
                description: 'Your notification preferences have been updated.',
            });

            setSettingsState(prev => ({
                ...prev,
                isSaving: false,
                hasChanges: false,
            }));
        } catch (error) {
            toast({
                title: 'Error saving settings',
                description: 'Please try again later.',
                variant: 'destructive',
            });
            setSettingsState(prev => ({ ...prev, isSaving: false }));
        }
    };

    if (settingsState.isLoading) {
        return (
            <div className="flex min-h-[400px] items-center justify-center">
                <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
                    <span>Loading settings…</span>
                </div>
            </div>
        );
    }

    return (
        <div className="container mx-auto py-8 px-4 max-w-4xl">
            <div className="mb-8">
                <h1 className="text-3xl font-bold">Settings</h1>
                <p className="text-muted-foreground mt-2">
                    Manage your notification preferences and account settings.
                </p>
            </div>

            <Tabs defaultValue="notifications" className="space-y-6">
                <TabsList className="grid w-full grid-cols-2 max-w-md">
                    <TabsTrigger value="notifications" className="flex items-center gap-2">
                        <Bell className="h-4 w-4" />
                        Notifications
                    </TabsTrigger>
                    <TabsTrigger value="profile" className="flex items-center gap-2">
                        <User className="h-4 w-4" />
                        Profile
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="notifications" className="space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Email Notifications</CardTitle>
                            <CardDescription>
                                Configure when you receive email notifications about dataset enrichment activities.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="email-version-complete">Version Enrichment Complete</Label>
                                    <p className="text-sm text-muted-foreground">
                                        Receive an email when a dataset version enrichment is completed.
                                    </p>
                                </div>
                                <Switch
                                    id="email-version-complete"
                                    checked={settingsState.notificationPreferences.emailOnVersionComplete}
                                    onCheckedChange={(checked) =>
                                        updateNotificationPreference('emailOnVersionComplete', checked)
                                    }
                                />
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="email-scan-complete">Scan Complete</Label>
                                    <p className="text-sm text-muted-foreground">
                                        Receive an email when an integration scan (SonarQube, Trivy) is completed.
                                    </p>
                                </div>
                                <Switch
                                    id="email-scan-complete"
                                    checked={settingsState.notificationPreferences.emailOnScanComplete}
                                    onCheckedChange={(checked) =>
                                        updateNotificationPreference('emailOnScanComplete', checked)
                                    }
                                />
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="email-version-failed">Enrichment Failed</Label>
                                    <p className="text-sm text-muted-foreground">
                                        Receive an email when a version enrichment or scan fails.
                                    </p>
                                </div>
                                <Switch
                                    id="email-version-failed"
                                    checked={settingsState.notificationPreferences.emailOnVersionFailed}
                                    onCheckedChange={(checked) =>
                                        updateNotificationPreference('emailOnVersionFailed', checked)
                                    }
                                />
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Browser Notifications</CardTitle>
                            <CardDescription>
                                Enable push notifications in your browser for real-time updates.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="browser-notifications">Enable Browser Notifications</Label>
                                    <p className="text-sm text-muted-foreground">
                                        Receive instant notifications when enrichment tasks complete.
                                    </p>
                                </div>
                                <Switch
                                    id="browser-notifications"
                                    checked={settingsState.notificationPreferences.browserNotifications}
                                    onCheckedChange={(checked) =>
                                        updateNotificationPreference('browserNotifications', checked)
                                    }
                                />
                            </div>
                        </CardContent>
                    </Card>

                    {settingsState.hasChanges && (
                        <div className="flex justify-end">
                            <Button
                                onClick={handleSaveSettings}
                                disabled={settingsState.isSaving}
                                className="min-w-[120px]"
                            >
                                {settingsState.isSaving ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Saving…
                                    </>
                                ) : (
                                    <>
                                        <Save className="mr-2 h-4 w-4" />
                                        Save Changes
                                    </>
                                )}
                            </Button>
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="profile" className="space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Profile Information</CardTitle>
                            <CardDescription>
                                Your account details from your authentication provider.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid gap-4">
                                <div className="space-y-2">
                                    <Label className="text-muted-foreground">Email</Label>
                                    <p className="font-medium">{user?.email || 'Not available'}</p>
                                </div>
                                <div className="space-y-2">
                                    <Label className="text-muted-foreground">Name</Label>
                                    <p className="font-medium">{user?.name || 'Not set'}</p>
                                </div>
                                <div className="space-y-2">
                                    <Label className="text-muted-foreground">Role</Label>
                                    <div className="flex items-center gap-2">
                                        <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                                            {user?.role?.toUpperCase() || 'GUEST'}
                                        </span>
                                        {user?.role === 'guest' && (
                                            <span className="text-sm text-muted-foreground">
                                                – Full access to dataset enrichment features
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <div className="pt-4 border-t">
                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                    <Check className="h-4 w-4 text-green-500" />
                                    <span>Signed in via Google OAuth</span>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}
