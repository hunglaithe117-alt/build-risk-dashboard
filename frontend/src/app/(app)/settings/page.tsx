'use client';

import { useState, useEffect, useCallback } from 'react';
import { Bell, Loader2, Save, User } from 'lucide-react';
import { useSearchParams, useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import { userSettingsApi, UpdateUserSettingsRequest } from '@/lib/api';
import { NotificationsList } from '@/components/notifications/NotificationsList';
import { ProfileSettings } from '@/components/settings/ProfileSettings';

interface SettingsState {
    browserNotifications: boolean;
    isLoading: boolean;
    isSaving: boolean;
    hasChanges: boolean;
}

export default function SettingsPage() {
    const { toast } = useToast();
    const searchParams = useSearchParams();
    const router = useRouter();

    const [activeTab, setActiveTab] = useState('notifications');

    const [settingsState, setSettingsState] = useState<SettingsState>({
        browserNotifications: true,
        isLoading: true,
        isSaving: false,
        hasChanges: false,
    });

    // Sync tab with URL
    useEffect(() => {
        const tab = searchParams.get('tab');
        if (tab && ['notifications', 'profile'].includes(tab)) {
            setActiveTab(tab);
        }
    }, [searchParams]);

    const handleTabChange = (value: string) => {
        setActiveTab(value);
        const params = new URLSearchParams(searchParams.toString());
        params.set('tab', value);
        router.push(`/settings?${params.toString()}`);
    };

    // Load user settings on mount
    const loadSettings = useCallback(async () => {
        try {
            const data = await userSettingsApi.get();
            setSettingsState((prev) => ({
                ...prev,
                browserNotifications: data.browser_notifications,
                isLoading: false,
            }));
        } catch {
            // Use defaults if API fails
            setSettingsState((prev) => ({
                ...prev,
                isLoading: false,
            }));
        }
    }, []);

    useEffect(() => {
        loadSettings();
    }, [loadSettings]);

    const handleSaveSettings = async () => {
        setSettingsState((prev) => ({ ...prev, isSaving: true }));

        try {
            const request: UpdateUserSettingsRequest = {
                browser_notifications: settingsState.browserNotifications,
            };
            await userSettingsApi.update(request);

            toast({
                title: 'Settings saved',
                description: 'Your preferences have been updated.',
            });

            setSettingsState((prev) => ({
                ...prev,
                isSaving: false,
                hasChanges: false,
            }));
        } catch {
            toast({
                title: 'Error saving settings',
                description: 'Please try again later.',
                variant: 'destructive',
            });
            setSettingsState((prev) => ({ ...prev, isSaving: false }));
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
                    Manage your notification preferences and view your profile.
                </p>
            </div>

            <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-6">
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
                    {/* Browser Notifications */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Bell className="h-5 w-5" />
                                Browser Notifications
                            </CardTitle>
                            <CardDescription>
                                Receive push notifications in your browser for real-time updates.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="browser-notifications">
                                        Enable Browser Notifications
                                    </Label>
                                    <p className="text-sm text-muted-foreground">
                                        Get instant notifications when important events occur.
                                    </p>
                                </div>
                                <Switch
                                    id="browser-notifications"
                                    checked={settingsState.browserNotifications}
                                    onCheckedChange={(checked) =>
                                        setSettingsState((prev) => ({
                                            ...prev,
                                            browserNotifications: checked,
                                            hasChanges: true,
                                        }))
                                    }
                                />
                            </div>
                        </CardContent>
                    </Card>

                    {/* Notification History */}
                    <NotificationsList />

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
                    <ProfileSettings />
                </TabsContent>
            </Tabs>
        </div>
    );
}
