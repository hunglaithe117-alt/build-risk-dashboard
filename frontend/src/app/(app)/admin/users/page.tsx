'use client'

import { useState, useEffect, useCallback } from 'react'
import { Users, Trash2, Shield, User, RefreshCw, Mail, Search, UserPlus, X, Clock, CheckCircle, XCircle, Send } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { adminUsersApi, adminInvitationsApi, usersApi } from '@/lib/api'
import type { UserAccount } from '@/types'
import type { Invitation, InvitationCreatePayload } from '@/lib/api'

export default function AdminUsersPage() {
    const [users, setUsers] = useState<UserAccount[]>([])
    const [invitations, setInvitations] = useState<Invitation[]>([])
    const [currentUserId, setCurrentUserId] = useState<string | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [isLoadingInvitations, setIsLoadingInvitations] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [searchQuery, setSearchQuery] = useState('')

    // Create invitation dialog state
    const [isInviteOpen, setIsInviteOpen] = useState(false)
    const [isInviting, setIsInviting] = useState(false)
    const [inviteForm, setInviteForm] = useState<InvitationCreatePayload>({
        email: '',
        github_username: '',
        role: 'guest',
    })

    // Delete dialog state
    const [deleteUserId, setDeleteUserId] = useState<string | null>(null)
    const [isDeleting, setIsDeleting] = useState(false)

    // Revoke invitation state
    const [revokeInvitationId, setRevokeInvitationId] = useState<string | null>(null)
    const [isRevoking, setIsRevoking] = useState(false)

    const fetchCurrentUser = useCallback(async () => {
        try {
            const currentUser = await usersApi.getCurrentUser()
            setCurrentUserId(currentUser.id)
        } catch (err) {
            console.error('Failed to get current user:', err)
        }
    }, [])

    const fetchUsers = useCallback(async () => {
        setIsLoading(true)
        setError(null)
        try {
            const response = await adminUsersApi.list(searchQuery || undefined)
            setUsers(response.items)
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to load users')
        } finally {
            setIsLoading(false)
        }
    }, [searchQuery])

    const fetchInvitations = useCallback(async () => {
        setIsLoadingInvitations(true)
        try {
            const response = await adminInvitationsApi.list()
            setInvitations(response.items)
        } catch (err: any) {
            console.error('Failed to load invitations:', err)
        } finally {
            setIsLoadingInvitations(false)
        }
    }, [])

    useEffect(() => {
        fetchCurrentUser()
    }, [fetchCurrentUser])

    useEffect(() => {
        fetchUsers()
    }, [fetchUsers])

    useEffect(() => {
        fetchInvitations()
    }, [fetchInvitations])

    const handleInviteUser = async () => {
        if (!inviteForm.email) return

        setIsInviting(true)
        setError(null)
        try {
            await adminInvitationsApi.create({
                email: inviteForm.email,
                github_username: inviteForm.github_username || undefined,
                role: inviteForm.role,
            })
            setIsInviteOpen(false)
            setInviteForm({ email: '', github_username: '', role: 'user' })
            fetchInvitations()
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to create invitation')
        } finally {
            setIsInviting(false)
        }
    }

    const handleRoleChange = async (userId: string, newRole: 'admin' | 'user') => {
        try {
            await adminUsersApi.updateRole(userId, newRole)
            fetchUsers()
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to update role')
        }
    }

    const handleDeleteUser = async () => {
        if (!deleteUserId) return

        setIsDeleting(true)
        try {
            await adminUsersApi.delete(deleteUserId)
            setDeleteUserId(null)
            fetchUsers()
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to delete user')
        } finally {
            setIsDeleting(false)
        }
    }

    const handleRevokeInvitation = async () => {
        if (!revokeInvitationId) return

        setIsRevoking(true)
        try {
            await adminInvitationsApi.revoke(revokeInvitationId)
            setRevokeInvitationId(null)
            fetchInvitations()
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to revoke invitation')
        } finally {
            setIsRevoking(false)
        }
    }

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString('vi-VN', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
        })
    }

    const getStatusBadge = (status: Invitation['status']) => {
        switch (status) {
            case 'pending':
                return <Badge variant="outline" className="text-yellow-600"><Clock className="h-3 w-3 mr-1" />Pending</Badge>
            case 'accepted':
                return <Badge variant="outline" className="text-green-600"><CheckCircle className="h-3 w-3 mr-1" />Accepted</Badge>
            case 'expired':
                return <Badge variant="outline" className="text-gray-500"><XCircle className="h-3 w-3 mr-1" />Expired</Badge>
            case 'revoked':
                return <Badge variant="outline" className="text-red-600"><X className="h-3 w-3 mr-1" />Revoked</Badge>
            default:
                return <Badge variant="outline">{status}</Badge>
        }
    }

    // Filter out current user from the list
    const filteredUsers = users.filter(user => user.id !== currentUserId)
    const pendingInvitations = invitations.filter(inv => inv.status === 'pending')

    return (
        <div className="flex flex-col gap-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Users className="h-6 w-6 text-muted-foreground" />
                    <div>
                        <h1 className="text-2xl font-bold">User Management</h1>
                        <p className="text-sm text-muted-foreground">
                            Manage user accounts and invitations
                        </p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => { fetchUsers(); fetchInvitations(); }} disabled={isLoading}>
                        <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                        Refresh
                    </Button>
                    <Dialog open={isInviteOpen} onOpenChange={setIsInviteOpen}>
                        <DialogTrigger asChild>
                            <Button size="sm">
                                <Send className="h-4 w-4 mr-2" />
                                Invite User
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>Invite New User</DialogTitle>
                                <DialogDescription>
                                    Send an invitation email to a user. They can login via GitHub after receiving the invitation.
                                </DialogDescription>
                            </DialogHeader>
                            <div className="grid gap-4 py-4">
                                <div className="grid gap-2">
                                    <Label htmlFor="email">Email *</Label>
                                    <Input
                                        id="email"
                                        type="email"
                                        placeholder="user@example.com"
                                        value={inviteForm.email}
                                        onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                                    />
                                </div>
                                <div className="grid gap-2">
                                    <Label htmlFor="github">GitHub Username (optional)</Label>
                                    <Input
                                        id="github"
                                        placeholder="octocat"
                                        value={inviteForm.github_username || ''}
                                        onChange={(e) => setInviteForm({ ...inviteForm, github_username: e.target.value })}
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        If provided, invitation will also match by GitHub username
                                    </p>
                                </div>
                                <div className="grid gap-2">
                                    <Label htmlFor="role">Role</Label>
                                    <div className="flex items-center gap-2 h-10 px-3 rounded-md border bg-muted">
                                        <User className="h-4 w-4 text-muted-foreground" />
                                        <span className="text-sm">Guest</span>
                                        <span className="text-xs text-muted-foreground">(read-only access)</span>
                                    </div>
                                </div>
                            </div>
                            <DialogFooter>
                                <Button variant="outline" onClick={() => setIsInviteOpen(false)}>
                                    Cancel
                                </Button>
                                <Button onClick={handleInviteUser} disabled={isInviting || !inviteForm.email}>
                                    {isInviting ? 'Sending...' : 'Send Invitation'}
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                </div>
            </div>

            {/* Error Alert */}
            {error && (
                <div className="bg-destructive/15 text-destructive px-4 py-3 rounded-md flex items-center justify-between">
                    <span>{error}</span>
                    <Button variant="ghost" size="sm" onClick={() => setError(null)}>
                        <X className="h-4 w-4" />
                    </Button>
                </div>
            )}

            {/* Tabs for Users and Invitations */}
            <Tabs defaultValue="users" className="w-full">
                <TabsList>
                    <TabsTrigger value="users">
                        Users ({filteredUsers.length})
                    </TabsTrigger>
                    <TabsTrigger value="invitations">
                        Pending Invitations ({pendingInvitations.length})
                    </TabsTrigger>
                </TabsList>

                {/* Users Tab */}
                <TabsContent value="users">
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle>Users</CardTitle>
                                    <CardDescription>
                                        All registered users (excluding yourself)
                                    </CardDescription>
                                </div>
                                <div className="relative w-64">
                                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                                    <Input
                                        placeholder="Search users..."
                                        value={searchQuery}
                                        onChange={(e) => setSearchQuery(e.target.value)}
                                        className="pl-8"
                                    />
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent>
                            {isLoading ? (
                                <div className="flex items-center justify-center py-8">
                                    <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                                </div>
                            ) : filteredUsers.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    {searchQuery ? 'No users found matching your search' : 'No other users found'}
                                </div>
                            ) : (
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>User</TableHead>
                                            <TableHead>Email</TableHead>
                                            <TableHead>Role</TableHead>
                                            <TableHead>Created</TableHead>
                                            <TableHead className="text-right">Actions</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {filteredUsers.map((user) => (
                                            <TableRow key={user.id}>
                                                <TableCell className="font-medium">
                                                    <div className="flex items-center gap-2">
                                                        {user.github?.avatar_url ? (
                                                            <img
                                                                src={user.github.avatar_url}
                                                                alt={user.name || user.email}
                                                                className="h-8 w-8 rounded-full"
                                                            />
                                                        ) : (
                                                            <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
                                                                <User className="h-4 w-4 text-muted-foreground" />
                                                            </div>
                                                        )}
                                                        <span>{user.name || user.github?.login || '-'}</span>
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <div className="flex items-center gap-1 text-muted-foreground">
                                                        <Mail className="h-3 w-3" />
                                                        <span className="text-sm">{user.email}</span>
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <Select
                                                        value={user.role}
                                                        onValueChange={(value: 'admin' | 'user') =>
                                                            handleRoleChange(user.id, value)
                                                        }
                                                    >
                                                        <SelectTrigger className="w-[100px]">
                                                            <SelectValue>
                                                                <Badge variant={user.role === 'admin' ? 'default' : 'secondary'}>
                                                                    {user.role === 'admin' ? (
                                                                        <Shield className="h-3 w-3 mr-1" />
                                                                    ) : (
                                                                        <User className="h-3 w-3 mr-1" />
                                                                    )}
                                                                    {user.role}
                                                                </Badge>
                                                            </SelectValue>
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            <SelectItem value="user">User</SelectItem>
                                                            <SelectItem value="admin">Admin</SelectItem>
                                                        </SelectContent>
                                                    </Select>
                                                </TableCell>
                                                <TableCell className="text-muted-foreground text-sm">
                                                    {formatDate(user.created_at)}
                                                </TableCell>
                                                <TableCell className="text-right">
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        className="text-destructive hover:text-destructive"
                                                        onClick={() => setDeleteUserId(user.id)}
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Invitations Tab */}
                <TabsContent value="invitations">
                    <Card>
                        <CardHeader>
                            <CardTitle>Pending Invitations</CardTitle>
                            <CardDescription>
                                Invitations waiting to be accepted. Invitations expire after 7 days.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {isLoadingInvitations ? (
                                <div className="flex items-center justify-center py-8">
                                    <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                                </div>
                            ) : pendingInvitations.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    <UserPlus className="h-12 w-12 mx-auto mb-3 text-muted-foreground/50" />
                                    <p>No pending invitations</p>
                                    <p className="text-sm">Click &quot;Invite User&quot; to invite someone</p>
                                </div>
                            ) : (
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Email</TableHead>
                                            <TableHead>GitHub</TableHead>
                                            <TableHead>Role</TableHead>
                                            <TableHead>Status</TableHead>
                                            <TableHead>Expires</TableHead>
                                            <TableHead className="text-right">Actions</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {pendingInvitations.map((invitation) => (
                                            <TableRow key={invitation.id}>
                                                <TableCell className="font-medium">
                                                    <div className="flex items-center gap-1">
                                                        <Mail className="h-3 w-3 text-muted-foreground" />
                                                        {invitation.email}
                                                    </div>
                                                </TableCell>
                                                <TableCell className="text-muted-foreground">
                                                    {invitation.github_username || '-'}
                                                </TableCell>
                                                <TableCell>
                                                    <Badge variant={invitation.role === 'admin' ? 'default' : 'secondary'}>
                                                        {invitation.role}
                                                    </Badge>
                                                </TableCell>
                                                <TableCell>
                                                    {getStatusBadge(invitation.status)}
                                                </TableCell>
                                                <TableCell className="text-muted-foreground text-sm">
                                                    {formatDate(invitation.expires_at)}
                                                </TableCell>
                                                <TableCell className="text-right">
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        className="text-destructive hover:text-destructive"
                                                        onClick={() => setRevokeInvitationId(invitation.id)}
                                                    >
                                                        <X className="h-4 w-4" />
                                                    </Button>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>

            {/* Delete User Confirmation Dialog */}
            <Dialog open={!!deleteUserId} onOpenChange={() => setDeleteUserId(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete User</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to delete this user? This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteUserId(null)}>
                            Cancel
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={handleDeleteUser}
                            disabled={isDeleting}
                        >
                            {isDeleting ? 'Deleting...' : 'Delete User'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Revoke Invitation Confirmation Dialog */}
            <Dialog open={!!revokeInvitationId} onOpenChange={() => setRevokeInvitationId(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Revoke Invitation</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to revoke this invitation? The user will no longer be able to use it to login.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setRevokeInvitationId(null)}>
                            Cancel
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={handleRevokeInvitation}
                            disabled={isRevoking}
                        >
                            {isRevoking ? 'Revoking...' : 'Revoke Invitation'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
