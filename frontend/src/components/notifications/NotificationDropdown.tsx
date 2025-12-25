'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell, Check, CheckCheck, ExternalLink } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { formatDistanceToNow } from 'date-fns'

import { notificationsApi } from '@/lib/api'
import type { Notification } from '@/types'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'

interface NotificationDropdownProps {
    className?: string
}

const NOTIFICATION_TYPE_ICONS: Record<string, string> = {
    pipeline_completed: '✅',
    pipeline_failed: '❌',
    dataset_import_completed: '📥',
    dataset_validation_completed: '✔️',
    dataset_enrichment_completed: '🔧',
    rate_limit_warning: '⏰',
    rate_limit_exhausted: '🚨',
    system: '💬',
}

export function NotificationDropdown({ className }: NotificationDropdownProps) {
    const router = useRouter()
    const [isOpen, setIsOpen] = useState(false)
    const [notifications, setNotifications] = useState<Notification[]>([])
    const [unreadCount, setUnreadCount] = useState(0)
    const [isLoading, setIsLoading] = useState(false)
    const dropdownRef = useRef<HTMLDivElement>(null)

    const fetchNotifications = useCallback(async () => {
        try {
            setIsLoading(true)
            const data = await notificationsApi.list({ limit: 10 })
            setNotifications(data.items)
            setUnreadCount(data.unread_count)
        } catch (err) {
            console.error('Failed to fetch notifications:', err)
        } finally {
            setIsLoading(false)
        }
    }, [])

    const fetchUnreadCount = useCallback(async () => {
        try {
            const count = await notificationsApi.getUnreadCount()
            setUnreadCount(count)
        } catch (err) {
            console.error('Failed to fetch unread count:', err)
        }
    }, [])

    const { authenticated } = useAuth()

    // Fetch unread count on mount and periodically
    useEffect(() => {
        if (!authenticated) return

        void fetchUnreadCount()
        const interval = setInterval(fetchUnreadCount, 30000) // Poll every 30s
        return () => clearInterval(interval)
    }, [fetchUnreadCount, authenticated])

    // Fetch full list when dropdown opens
    useEffect(() => {
        if (isOpen) {
            void fetchNotifications()
        }
    }, [isOpen, fetchNotifications])

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false)
            }
        }

        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [])

    const handleNotificationClick = async (notification: Notification) => {
        try {
            if (!notification.is_read) {
                await notificationsApi.markAsRead(notification.id)
                setNotifications((prev) =>
                    prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n))
                )
                setUnreadCount((prev) => Math.max(0, prev - 1))
            }

            if (notification.link) {
                setIsOpen(false)
                router.push(notification.link)
            }
        } catch (err) {
            console.error('Failed to mark notification as read:', err)
        }
    }

    const handleMarkAllAsRead = async () => {
        try {
            await notificationsApi.markAllAsRead()
            setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
            setUnreadCount(0)
        } catch (err) {
            console.error('Failed to mark all as read:', err)
        }
    }

    return (
        <div className={cn('relative', className)} ref={dropdownRef}>
            {/* Bell Button */}
            <button
                className="relative rounded-full p-2 text-muted-foreground transition hover:bg-slate-100 hover:text-blue-600 dark:hover:bg-slate-800"
                aria-label="Notifications"
                type="button"
                onClick={() => setIsOpen(!isOpen)}
            >
                <Bell className="h-5 w-5" />
                {unreadCount > 0 && (
                    <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
                        {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                )}
            </button>

            {/* Dropdown */}
            {isOpen && (
                <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border bg-white shadow-lg dark:bg-slate-900">
                    {/* Header */}
                    <div className="flex items-center justify-between border-b px-4 py-3">
                        <h3 className="font-semibold">Notifications</h3>
                        {unreadCount > 0 && (
                            <button
                                className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
                                onClick={handleMarkAllAsRead}
                                type="button"
                            >
                                <CheckCheck className="h-3 w-3" />
                                Mark all read
                            </button>
                        )}
                    </div>

                    {/* Notification List */}
                    <div className="max-h-80 overflow-y-auto">
                        {isLoading ? (
                            <div className="flex items-center justify-center py-8">
                                <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
                            </div>
                        ) : notifications.length === 0 ? (
                            <div className="py-8 text-center text-sm text-muted-foreground">
                                No notifications yet
                            </div>
                        ) : (
                            <ul>
                                {notifications.map((notification) => (
                                    <li
                                        key={notification.id}
                                        className={cn(
                                            'cursor-pointer border-b px-4 py-3 transition hover:bg-slate-50 dark:hover:bg-slate-800',
                                            !notification.is_read && 'bg-blue-50/50 dark:bg-blue-900/20'
                                        )}
                                        onClick={() => handleNotificationClick(notification)}
                                        onKeyDown={(e) => e.key === 'Enter' && handleNotificationClick(notification)}
                                        role="button"
                                        tabIndex={0}
                                    >
                                        <div className="flex items-start gap-3">
                                            <span className="text-lg">
                                                {NOTIFICATION_TYPE_ICONS[notification.type] || '📌'}
                                            </span>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <p className="text-sm font-medium truncate">{notification.title}</p>
                                                    {!notification.is_read && (
                                                        <span className="h-2 w-2 rounded-full bg-blue-600 shrink-0" />
                                                    )}
                                                </div>
                                                <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                                                    {notification.message}
                                                </p>
                                                <p className="text-xs text-muted-foreground mt-1">
                                                    {formatDistanceToNow(new Date(notification.created_at), { addSuffix: true })}
                                                </p>
                                            </div>
                                            {notification.link && (
                                                <ExternalLink className="h-3 w-3 text-muted-foreground shrink-0 mt-1" />
                                            )}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>

                    {/* Footer */}
                    {notifications.length > 0 && (
                        <div className="border-t px-4 py-2 text-center">
                            <button
                                className="text-xs text-blue-600 hover:text-blue-800"
                                type="button"
                                onClick={() => {
                                    setIsOpen(false)
                                    router.push('/settings')
                                }}
                            >
                                View all notifications
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
