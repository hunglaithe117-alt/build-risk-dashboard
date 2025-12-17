'use client'

import { useState, useEffect, useCallback } from 'react'
import { Save, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { useToast } from '@/components/ui/use-toast'
import { settingsApi } from '@/lib/api'
import type { ApplicationSettings } from '@/types'

interface MetricInfo {
  key: string
  display_name: string
  description: string
  data_type: string
}

interface AvailableMetrics {
  sonarqube: {
    metrics: Record<string, MetricInfo[]>
    all_keys: string[]
  }
  trivy: {
    metrics: Record<string, MetricInfo[]>
    all_keys: string[]
  }
}

interface MetricsSectionProps {
  title: string
  metricsData: { metrics: Record<string, MetricInfo[]>; all_keys: string[] }
  enabledMetrics: string[]
  onToggleMetric: (key: string) => void
  onSelectAll: () => void
  onSelectNone: () => void
}

function MetricsSection({
  title,
  metricsData,
  enabledMetrics,
  onToggleMetric,
  onSelectAll,
  onSelectNone,
}: MetricsSectionProps) {
  const [expanded, setExpanded] = useState(false)
  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({})

  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) => ({ ...prev, [category]: !prev[category] }))
  }

  const allSelected = enabledMetrics.length === 0 || enabledMetrics.length === metricsData.all_keys.length
  const noneSelected = enabledMetrics.length > 0 && enabledMetrics.length === 0
  const selectedCount = enabledMetrics.length === 0 ? metricsData.all_keys.length : enabledMetrics.length

  const isMetricEnabled = (key: string) => {
    // Empty array means all metrics enabled
    return enabledMetrics.length === 0 || enabledMetrics.includes(key)
  }

  return (
    <div className="border rounded-lg p-3 mt-4">
      <button
        type="button"
        className="flex items-center justify-between w-full text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="font-medium text-sm">
          {title} ({selectedCount}/{metricsData.all_keys.length} metrics)
        </span>
        {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>

      {expanded && (
        <div className="mt-3 space-y-3">
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onSelectAll}>
              Select All
            </Button>
            <Button variant="outline" size="sm" onClick={onSelectNone}>
              Select None
            </Button>
          </div>

          {Object.entries(metricsData.metrics).map(([category, metrics]) => (
            <div key={category} className="border-t pt-2">
              <button
                type="button"
                className="flex items-center gap-2 text-sm font-medium text-muted-foreground capitalize w-full text-left"
                onClick={() => toggleCategory(category)}
              >
                {expandedCategories[category] ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                {category.replace(/_/g, ' ')} ({metrics.length})
              </button>

              {expandedCategories[category] && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2 pl-5">
                  {metrics.map((metric) => (
                    <label
                      key={metric.key}
                      className="flex items-start gap-2 text-sm cursor-pointer hover:bg-muted/50 p-1 rounded"
                    >
                      <Checkbox
                        checked={isMetricEnabled(metric.key)}
                        onCheckedChange={() => onToggleMetric(metric.key)}
                        className="mt-0.5"
                      />
                      <div>
                        <span className="font-medium">{metric.display_name}</span>
                        <p className="text-xs text-muted-foreground">{metric.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function IntegrationsTab() {
  const [settings, setSettings] = useState<ApplicationSettings | null>(null)
  const [availableMetrics, setAvailableMetrics] = useState<AvailableMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const [settingsData, metricsData] = await Promise.all([
        settingsApi.get(),
        settingsApi.getAvailableMetrics(),
      ])
      setSettings(settingsData)
      setAvailableMetrics(metricsData)
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

  const toggleSonarMetric = useCallback(
    (key: string) => {
      if (!settings || !availableMetrics) return

      let newMetrics: string[]
      const currentMetrics = settings.sonarqube.enabled_metrics

      if (currentMetrics.length === 0) {
        // Currently all enabled - switch to explicit list minus the toggled one
        newMetrics = availableMetrics.sonarqube.all_keys.filter((k) => k !== key)
      } else if (currentMetrics.includes(key)) {
        // Remove from list
        newMetrics = currentMetrics.filter((k) => k !== key)
      } else {
        // Add to list
        newMetrics = [...currentMetrics, key]
      }

      // If all metrics are selected, set to empty array (means all)
      if (newMetrics.length === availableMetrics.sonarqube.all_keys.length) {
        newMetrics = []
      }

      setSettings({
        ...settings,
        sonarqube: { ...settings.sonarqube, enabled_metrics: newMetrics },
      })
    },
    [settings, availableMetrics]
  )

  const toggleTrivyMetric = useCallback(
    (key: string) => {
      if (!settings || !availableMetrics) return

      let newMetrics: string[]
      const currentMetrics = settings.trivy.enabled_metrics

      if (currentMetrics.length === 0) {
        newMetrics = availableMetrics.trivy.all_keys.filter((k) => k !== key)
      } else if (currentMetrics.includes(key)) {
        newMetrics = currentMetrics.filter((k) => k !== key)
      } else {
        newMetrics = [...currentMetrics, key]
      }

      if (newMetrics.length === availableMetrics.trivy.all_keys.length) {
        newMetrics = []
      }

      setSettings({
        ...settings,
        trivy: { ...settings.trivy, enabled_metrics: newMetrics },
      })
    },
    [settings, availableMetrics]
  )

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
          <div className="flex items-center justify-between">
            <Label htmlFor="sonar-enabled">Enable SonarQube</Label>
            <Switch
              id="sonar-enabled"
              checked={settings.sonarqube.enabled}
              onCheckedChange={(checked) =>
                setSettings({ ...settings, sonarqube: { ...settings.sonarqube, enabled: checked } })
              }
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
              <Label htmlFor="sonar-project-key">Default Project Key</Label>
              <Input
                id="sonar-project-key"
                value={settings.sonarqube.default_project_key || ''}
                onChange={(e) =>
                  setSettings({ ...settings, sonarqube: { ...settings.sonarqube, default_project_key: e.target.value } })
                }
                placeholder="build-risk-ui"
              />
            </div>
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

          {/* SonarQube Metrics Selection */}
          {availableMetrics && (
            <MetricsSection
              title="Metrics to Collect"
              metricsData={availableMetrics.sonarqube}
              enabledMetrics={settings.sonarqube.enabled_metrics}
              onToggleMetric={toggleSonarMetric}
              onSelectAll={() =>
                setSettings({ ...settings, sonarqube: { ...settings.sonarqube, enabled_metrics: [] } })
              }
              onSelectNone={() =>
                setSettings({ ...settings, sonarqube: { ...settings.sonarqube, enabled_metrics: ['__none__'] } })
              }
            />
          )}
        </CardContent>
      </Card>

      {/* CircleCI */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">CircleCI</CardTitle>
          <CardDescription>CircleCI integration for build data</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="circleci-enabled">Enable CircleCI</Label>
            <Switch
              id="circleci-enabled"
              checked={settings.circleci.enabled}
              onCheckedChange={(checked) =>
                setSettings({ ...settings, circleci: { ...settings.circleci, enabled: checked } })
              }
            />
          </div>
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
          <div className="flex items-center justify-between">
            <Label htmlFor="travis-enabled">Enable Travis CI</Label>
            <Switch
              id="travis-enabled"
              checked={settings.travis.enabled}
              onCheckedChange={(checked) =>
                setSettings({ ...settings, travis: { ...settings.travis, enabled: checked } })
              }
            />
          </div>
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
          <div className="flex items-center justify-between">
            <Label htmlFor="trivy-enabled">Enable Trivy</Label>
            <Switch
              id="trivy-enabled"
              checked={settings.trivy.enabled}
              onCheckedChange={(checked) =>
                setSettings({ ...settings, trivy: { ...settings.trivy, enabled: checked } })
              }
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="trivy-severity">Severity Levels</Label>
              <Input
                id="trivy-severity"
                value={settings.trivy.severity}
                onChange={(e) =>
                  setSettings({ ...settings, trivy: { ...settings.trivy, severity: e.target.value } })
                }
                placeholder="CRITICAL,HIGH,MEDIUM"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="trivy-timeout">Timeout (seconds)</Label>
              <Input
                id="trivy-timeout"
                type="number"
                value={settings.trivy.timeout || 300}
                onChange={(e) =>
                  setSettings({ ...settings, trivy: { ...settings.trivy, timeout: parseInt(e.target.value) || 300 } })
                }
                placeholder="300"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="trivy-skip-dirs">Skip Directories</Label>
            <Input
              id="trivy-skip-dirs"
              value={settings.trivy.skip_dirs || ''}
              onChange={(e) =>
                setSettings({ ...settings, trivy: { ...settings.trivy, skip_dirs: e.target.value } })
              }
              placeholder="node_modules,vendor,.git"
            />
            <p className="text-xs text-muted-foreground">Comma-separated list of directories to skip during scanning</p>
          </div>

          {/* Trivy Metrics Selection */}
          {availableMetrics && (
            <MetricsSection
              title="Metrics to Collect"
              metricsData={availableMetrics.trivy}
              enabledMetrics={settings.trivy.enabled_metrics}
              onToggleMetric={toggleTrivyMetric}
              onSelectAll={() =>
                setSettings({ ...settings, trivy: { ...settings.trivy, enabled_metrics: [] } })
              }
              onSelectNone={() =>
                setSettings({ ...settings, trivy: { ...settings.trivy, enabled_metrics: ['__none__'] } })
              }
            />
          )}
        </CardContent>
      </Card>

      {/* Save Button - Sticky bottom bar like Vercel/GitHub Settings */}
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
