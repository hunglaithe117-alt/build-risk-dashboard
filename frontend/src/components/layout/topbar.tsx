'use client'

import { Bell, Github, LogOut, Settings } from 'lucide-react'
import Image from 'next/image'

const user = {
  name: 'Hung Lai',
  role: 'DevSecOps Researcher',
  avatar: 'https://avatars.githubusercontent.com/u/9919?s=200&v=4',
}

export function Topbar() {
  return (
    <header className="flex h-16 items-center justify-between border-b bg-white/70 px-6 backdrop-blur dark:bg-slate-950/90">
      <div>
        <h1 className="text-lg font-semibold text-foreground">BuildGuard Dashboard</h1>
          <p className="text-xs text-muted-foreground">
          Track builds & extracted features · GitHub OAuth with read access to workflow data
        </p>
      </div>

      <div className="flex items-center gap-4">
        <button
          className="flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          type="button"
        >
          <Github className="h-4 w-4" />
          buildguard
        </button>

        <div className="flex items-center gap-3">
          <button
            className="rounded-full p-2 text-muted-foreground transition hover:bg-slate-100 hover:text-blue-600 dark:hover:bg-slate-800"
            aria-label="Notifications"
            type="button"
          >
            <Bell className="h-5 w-5" />
          </button>
          <button
            className="rounded-full p-2 text-muted-foreground transition hover:bg-slate-100 hover:text-blue-600 dark:hover:bg-slate-800"
            aria-label="Settings"
            type="button"
          >
            <Settings className="h-5 w-5" />
          </button>
        </div>

        <div className="flex items-center gap-3 rounded-xl border px-3 py-2">
          <div className="relative h-8 w-8 overflow-hidden rounded-full bg-slate-200">
            <Image src={user.avatar} alt={user.name} fill className="object-cover" />
          </div>
          <div>
            <p className="text-sm font-semibold">{user.name}</p>
            <p className="text-xs text-muted-foreground">{user.role}</p>
          </div>
          <button
            className="rounded-full border border-slate-200 p-2 text-muted-foreground transition hover:bg-red-50 hover:text-red-600 dark:border-slate-700 dark:hover:bg-red-900/30 dark:hover:text-red-400"
            aria-label="Sign out"
            type="button"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  )
}
