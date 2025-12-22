'use client'

import { useState, useEffect } from 'react'
import { Save, Loader2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/use-toast'
import { settingsApi } from '@/lib/api'
import type { ApplicationSettings } from '@/types'

export function IntegrationsTab() {
  const [settings, setSettings] = useState<ApplicationSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const settingsData = await settingsApi.get()
      setSettings(settingsData)
    } catch (error) {
      toast({ title: 'Failed to load settings', variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!settings) return

    setSaving(true)
    try {
      await settingsApi.update(settings)
      toast({ title: 'Settings saved successfully' })
    } catch (error) {
      toast({ title: 'Failed to save settings', variant: 'destructive' })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    )
  }

  if (!settings) return null

  return (
    <div className="space-y-6">
      {/* SonarQube */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">SonarQube</CardTitle>
          <CardDescription>Code quality and security analysis</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="sonar-url">Host URL</Label>
            <Input
              id="sonar-url"
              value={settings.sonarqube.host_url}
              onChange={(e) =>
                setSettings({ ...settings, sonarqube: { ...settings.sonarqube, host_url: e.target.value } })
              }
              placeholder="http://localhost:9000"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sonar-token">Authentication Token</Label>
            <Input
              id="sonar-token"
              type="password"
              value={settings.sonarqube.token || ''}
              onChange={(e) =>
                setSettings({ ...settings, sonarqube: { ...settings.sonarqube, token: e.target.value } })
              }
              placeholder="Enter token to update"
            />
          </div>

          {/* Webhook Settings */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="sonar-webhook-url">Webhook URL (required in SonarQube)</Label>
              <Input
                id="sonar-webhook-url"
                value={settings.sonarqube.webhook_url || ''}
                readOnly
                className="bg-muted cursor-not-allowed"
              />
              <p className="text-xs text-muted-foreground">
                Copy this URL to SonarQube → Administration → Webhooks
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="sonar-webhook-secret">Webhook Secret</Label>
              <Input
                id="sonar-webhook-secret"
                type="password"
                value={settings.sonarqube.webhook_secret || ''}
                onChange={(e) =>
                  setSettings({ ...settings, sonarqube: { ...settings.sonarqube, webhook_secret: e.target.value } })
                }
                placeholder="Enter secret to update"
              />
            </div>
          </div>

          {/* Default Config */}
          <div className="space-y-2">
            <Label htmlFor="sonar-default-config">Default sonar-project.properties</Label>
            <Textarea
              id="sonar-default-config"
              value={settings.sonarqube.default_config || ''}
              onChange={(e) =>
                setSettings({ ...settings, sonarqube: { ...settings.sonarqube, default_config: e.target.value } })
              }
              placeholder="# sonar-project.properties content..."
              className="font-mono text-sm min-h-[200px]"
            />
            <p className="text-xs text-muted-foreground">
              Default configuration used when no custom config is provided during scan
            </p>
          </div>
        </CardContent>
      </Card>

      {/* CircleCI */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">CircleCI</CardTitle>
          <CardDescription>CircleCI integration for build data</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="circleci-url">API Base URL</Label>
            <Input
              id="circleci-url"
              value={settings.circleci.base_url || ''}
              onChange={(e) =>
                setSettings({ ...settings, circleci: { ...settings.circleci, base_url: e.target.value } })
              }
              placeholder="https://circleci.com/api/v2"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="circleci-token">API Token</Label>
            <Input
              id="circleci-token"
              type="password"
              value={settings.circleci.token || ''}
              onChange={(e) =>
                setSettings({ ...settings, circleci: { ...settings.circleci, token: e.target.value } })
              }
              placeholder="Enter token to update"
            />
          </div>
        </CardContent>
      </Card>

      {/* Travis CI */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Travis CI</CardTitle>
          <CardDescription>Travis CI integration for build data</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="travis-url">API Base URL</Label>
            <Input
              id="travis-url"
              value={settings.travis.base_url || ''}
              onChange={(e) =>
                setSettings({ ...settings, travis: { ...settings.travis, base_url: e.target.value } })
              }
              placeholder="https://api.travis-ci.com"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="travis-token">API Token</Label>
            <Input
              id="travis-token"
              type="password"
              value={settings.travis.token || ''}
              onChange={(e) =>
                setSettings({ ...settings, travis: { ...settings.travis, token: e.target.value } })
              }
              placeholder="Enter token to update"
            />
          </div>
        </CardContent>
      </Card>

      {/* Trivy Security Scanner */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Trivy Security Scanner</CardTitle>
          <CardDescription>Container and dependency security scanning</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="trivy-server-url">Server URL (optional)</Label>
            <Input
              id="trivy-server-url"
              value={settings.trivy.server_url || ''}
              onChange={(e) =>
                setSettings({ ...settings, trivy: { ...settings.trivy, server_url: e.target.value || null } })
              }
              placeholder="http://trivy:4954 (leave empty for standalone mode)"
            />
            <p className="text-xs text-muted-foreground">
              For client/server mode. Leave empty to run Trivy via Docker directly.
            </p>
          </div>

          {/* Default Config */}
          <div className="space-y-2">
            <Label htmlFor="trivy-default-config">Default trivy.yaml</Label>
            <Textarea
              id="trivy-default-config"
              value={settings.trivy.default_config || ''}
              onChange={(e) =>
                setSettings({ ...settings, trivy: { ...settings.trivy, default_config: e.target.value } })
              }
              placeholder="# trivy.yaml content..."
              className="font-mono text-sm min-h-[250px]"
            />
            <p className="text-xs text-muted-foreground">
              Default configuration used when no custom config is provided during scan
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Save Button - Sticky bottom bar */}
      <div className="fixed bottom-0 left-0 right-0 z-50 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:left-[280px]">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between px-4 py-3 lg:px-6">
          <p className="text-sm text-muted-foreground">
            {saving ? 'Saving changes...' : 'Make sure to save your changes'}
          </p>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            Save Changes
          </Button>
        </div>
      </div>

      {/* Spacer to prevent content being hidden behind fixed bar */}
      <div className="h-20" />
    </div>
  )
}
