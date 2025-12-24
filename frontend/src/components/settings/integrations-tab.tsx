'use client'

import { useState, useEffect } from 'react'
import { Save, Loader2, AlertCircle } from 'lucide-react'
import Editor from '@monaco-editor/react'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
      <Accordion type="single" collapsible className="w-full" defaultValue="sonarqube">
        {/* SonarQube */}
        <AccordionItem value="sonarqube">
          <AccordionTrigger className="text-base font-semibold">
            SonarQube Integration
          </AccordionTrigger>
          <AccordionContent className="space-y-6 pt-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="sonar-url">Host URL</Label>
                <Input
                  id="sonar-url"
                  value={settings.sonarqube.host_url}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      sonarqube: { ...settings.sonarqube, host_url: e.target.value },
                    })
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
                    setSettings({
                      ...settings,
                      sonarqube: { ...settings.sonarqube, token: e.target.value },
                    })
                  }
                  placeholder="Enter token to update"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="sonar-webhook-secret">Webhook Secret</Label>
              <Input
                id="sonar-webhook-secret"
                type="password"
                value={settings.sonarqube.webhook_secret || ''}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    sonarqube: {
                      ...settings.sonarqube,
                      webhook_secret: e.target.value,
                    },
                  })
                }
                placeholder="Enter secret to update"
              />
              <p className="text-xs text-muted-foreground">
                Secret used to verify webhook payloads from SonarQube.
              </p>
            </div>

            <div className="space-y-2">
              <Label>Default sonar-project.properties</Label>
              <div className="h-[300px] overflow-hidden rounded-md border">
                <Editor
                  height="100%"
                  defaultLanguage="properties"
                  value={settings.sonarqube.default_config || ''}
                  onChange={(value) =>
                    setSettings({
                      ...settings,
                      sonarqube: {
                        ...settings.sonarqube,
                        default_config: value || '',
                      },
                    })
                  }
                  options={{
                    minimap: { enabled: false },
                    fontSize: 13,
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                  }}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Default configuration used when no custom config is provided during scan.
              </p>
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* Trivy Scanner */}
        <AccordionItem value="trivy">
          <AccordionTrigger className="text-base font-semibold">
            Trivy Security Scanner
          </AccordionTrigger>
          <AccordionContent className="space-y-6 pt-4">
            <div className="space-y-2">
              <Label htmlFor="trivy-server-url">Server URL (Optional)</Label>
              <Input
                id="trivy-server-url"
                value={settings.trivy.server_url || ''}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    trivy: { ...settings.trivy, server_url: e.target.value || null },
                  })
                }
                placeholder="http://trivy:4954"
              />
              <p className="text-xs text-muted-foreground">
                Leave empty to run Trivy in standalone mode (via Docker).
              </p>
            </div>

            <div className="space-y-2">
              <Label>Default trivy.yaml</Label>
              <div className="h-[300px] overflow-hidden rounded-md border">
                <Editor
                  height="100%"
                  defaultLanguage="yaml"
                  value={settings.trivy.default_config || ''}
                  onChange={(value) =>
                    setSettings({
                      ...settings,
                      trivy: { ...settings.trivy, default_config: value || '' },
                    })
                  }
                  options={{
                    minimap: { enabled: false },
                    fontSize: 13,
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                  }}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Default configuration used when no custom config is provided during scan.
              </p>
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* CI Providers */}
        <AccordionItem value="ci-providers">
          <AccordionTrigger className="text-base font-semibold">
            CI Providers (CircleCI / Travis)
          </AccordionTrigger>
          <AccordionContent className="space-y-6 pt-4">
            <div className="space-y-4">
              <h4 className="font-medium">CircleCI</h4>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="circleci-url">API Base URL</Label>
                  <Input
                    id="circleci-url"
                    value={settings.circleci.base_url || ''}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        circleci: { ...settings.circleci, base_url: e.target.value },
                      })
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
                      setSettings({
                        ...settings,
                        circleci: { ...settings.circleci, token: e.target.value },
                      })
                    }
                    placeholder="Enter token to update"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-4 pt-4 border-t">
              <h4 className="font-medium">Travis CI</h4>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="travis-url">API Base URL</Label>
                  <Input
                    id="travis-url"
                    value={settings.travis.base_url || ''}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        travis: { ...settings.travis, base_url: e.target.value },
                      })
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
                      setSettings({
                        ...settings,
                        travis: { ...settings.travis, token: e.target.value },
                      })
                    }
                    placeholder="Enter token to update"
                  />
                </div>
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      {/* Save Button - Sticky bottom bar */}
      <div className="fixed bottom-0 left-0 right-0 z-50 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:left-[280px]">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between px-4 py-3 lg:px-6">
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <AlertCircle className="h-4 w-4" />
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
