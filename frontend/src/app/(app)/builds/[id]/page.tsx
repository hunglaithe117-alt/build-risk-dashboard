import { notFound } from 'next/navigation'

import { buildApi } from '@/lib/api'
import type { BuildDetail } from '@/types'
import { BuildDetailClient } from './view'

interface BuildDetailPageProps {
  params: { id: string }
}

async function fetchBuildDetail(id: string): Promise<BuildDetail | null> {
  try {
    const build = await buildApi.getById(id)
    return build
  } catch (error) {
    console.error('Failed to load build detail', error)
    return null
  }
}

export default async function BuildDetailPage({ params }: BuildDetailPageProps) {
  const buildId = params.id
  if (!buildId) {
    notFound()
  }

  const build = await fetchBuildDetail(buildId)

  if (!build) {
    notFound()
  }

  return <BuildDetailClient build={build} />
}
