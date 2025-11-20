import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { AuthProvider } from '@/contexts/auth-context'
import { WebSocketProvider } from '@/contexts/websocket-context'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Build Risk Assessment - CI/CD Monitor',
  description: 'Monitor CI/CD builds and collect commit/workflow metadata for feature extraction',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <AuthProvider>
          <WebSocketProvider>{children}</WebSocketProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
