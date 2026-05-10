import {
  Brain,
  Cloud,
  Monitor,
  Zap,
  Globe,
  Languages,
  Code,
} from 'lucide-react'
import type * as React from 'react'
import { cn } from '@/lib/utils'

type ProviderIconProps = {
  providerId: string
  className?: string
}

type LucideIconType = React.ComponentType<React.SVGProps<SVGSVGElement>>

function getIcon(providerId: string): LucideIconType {
  const normalized = providerId.toLowerCase().trim()

  if (normalized === 'anthropic') return Brain
  if (normalized === 'openai') return Code
  if (normalized === 'google') return Languages
  if (normalized === 'openrouter') return Globe
  if (normalized === 'minimax') return Zap
  if (normalized === 'ollama') return Monitor
  return Cloud
}

export default function ProviderIcon({ providerId, className }: ProviderIconProps) {
  const Icon = getIcon(providerId)
  return <Icon className={cn('h-5 w-5 shrink-0', className)} />
}
