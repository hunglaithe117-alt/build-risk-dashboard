'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/contexts/auth-context'
import { usersApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/components/ui/use-toast'
import Image from 'next/image'
import { Loader2 } from 'lucide-react'

export default function ProfilePage() {
    const { user: authUser, refresh, githubProfile } = useAuth()
    const { toast } = useToast()

    const [name, setName] = useState('')
    const [loading, setLoading] = useState(false)
    const [saving, setSaving] = useState(false)

    // Initialize form with current user data
    useEffect(() => {
        if (authUser) {
            setName(authUser.name || '')
        }
    }, [authUser])

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setSaving(true)
        try {
            await usersApi.updateCurrentUser({ name })
            await refresh() // Refresh auth context to update UI globally
            toast({
                title: "Profile updated",
                description: "Your profile information has been updated successfully.",
            })
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to update profile. Please try again.",
                variant: "destructive",
            })
        } finally {
            setSaving(false)
        }
    }

    if (!authUser) {
        return (
            <div className="flex h-screen items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        )
    }

    return (
        <div className="container max-w-2xl py-10">
            <h1 className="mb-8 text-3xl font-bold">Profile Settings</h1>

            <div className="grid gap-6">
                {/* Profile Information Card */}
                <Card>
                    <CardHeader>
                        <CardTitle>Personal Information</CardTitle>
                        <CardDescription>
                            Manage your profile details. Some information is managed by GitHub.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form onSubmit={handleSubmit} className="space-y-6">

                            {/* Avatar Section */}
                            <div className="flex items-center gap-4">
                                <div className="relative h-20 w-20 overflow-hidden rounded-full border bg-muted">
                                    {githubProfile?.avatar_url ? (
                                        <Image
                                            src={githubProfile.avatar_url}
                                            alt="Avatar"
                                            fill
                                            className="object-cover"
                                        />
                                    ) : (
                                        <div className="flex h-full w-full items-center justify-center bg-slate-200 text-2xl font-bold text-slate-500">
                                            {authUser.name?.[0]?.toUpperCase() || authUser.email[0].toUpperCase()}
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <h3 className="font-medium">Profile Picture</h3>
                                    <p className="text-sm text-muted-foreground">
                                        Managed by GitHub
                                    </p>
                                </div>
                            </div>

                            {/* Email Field (Read-only) */}
                            <div className="space-y-2">
                                <Label htmlFor="email">Email</Label>
                                <Input
                                    id="email"
                                    value={authUser.email}
                                    disabled
                                    className="bg-muted"
                                />
                                <p className="text-xs text-muted-foreground">
                                    Email authentication is managed via GitHub.
                                </p>
                            </div>

                            {/* Name Field (Editable) */}
                            <div className="space-y-2">
                                <Label htmlFor="name">Display Name</Label>
                                <Input
                                    id="name"
                                    value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    placeholder="Your display name"
                                />
                            </div>

                            {/* Role Field (Read-only) */}
                            <div className="space-y-2">
                                <Label htmlFor="role">Role</Label>
                                <Input
                                    id="role"
                                    value={authUser.role?.toUpperCase() || 'USER'}
                                    disabled
                                    className="bg-muted"
                                />
                            </div>

                            {/* Repo Access Summary */}
                            {authUser.github_accessible_repos && (
                                <div className="space-y-2">
                                    <Label>GitHub Access</Label>
                                    <div className="rounded-md border bg-muted p-3 text-sm text-muted-foreground">
                                        You have access to <strong>{authUser.github_accessible_repos.length}</strong> repositories linked to this organization.
                                    </div>
                                </div>
                            )}

                            <div className="flex justify-end">
                                <Button type="submit" disabled={saving}>
                                    {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Save Changes
                                </Button>
                            </div>

                        </form>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
