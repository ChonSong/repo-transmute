import { Code, Brain, Puzzle } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useState } from 'react'

interface ProfileSummary {
  name: string
  model?: string
  active?: boolean
}

interface SuggestionChip {
  label: string
  prompt: string
  icon: typeof Code
}

const SUGGESTIONS: Array<SuggestionChip> = [
  {
    label: 'Analyze workspace',
    prompt:
      'Analyze this workspace structure and give me 3 engineering risks. Use tools and keep it concise.',
    icon: Code,
  },
  {
    label: 'Save a preference',
    prompt:
      'Save this to memory exactly: "For demos, respond in 3 bullets max and put risk first." Then confirm saved.',
    icon: Brain,
  },
  {
    label: 'Create a file',
    prompt: 'Create demo-checklist.md with 5 launch checks for this app.',
    icon: Puzzle,
  },
]

interface ChatEmptyStateProps {
  onSuggestionClick?: (prompt: string) => void
  compact?: boolean
}

export default function ChatEmptyState({
  onSuggestionClick,
  compact = false,
}: ChatEmptyStateProps) {
  const [activeProfile, setActiveProfile] = useState<ProfileSummary | null>(null)

  useEffect(() => {
    fetch('/api/profiles/list')
      .then((res) => res.json())
      .then((data) => {
        const profiles = data?.profiles as Array<ProfileSummary> | undefined
        const active = profiles?.find((p) => p.active)
        if (active) setActiveProfile(active)
      })
      .catch(() => {
        // silently ignore — profile info is cosmetic
      })
  }, [])

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex h-full flex-col items-center justify-center px-4 py-8"
    >
      <div className="flex max-w-xl flex-col items-center text-center">
        <div className="relative mb-6">
          <img
            src="/claude-avatar.webp"
            alt="Hermes Agent"
            className="relative size-20 rounded-md"
            style={{
              border: '1px solid var(--theme-border)',
              padding: '4px',
              background: 'var(--theme-card)',
            }}
          />
        </div>

        <p
          className="micro-label mb-2"
          style={{ color: 'var(--theme-muted)' }}
        >
          Hermes Workspace
        </p>

        <h2
          className="editorial-display text-3xl"
          style={{ color: 'var(--theme-text)' }}
        >
          Begin a session
        </h2>

        {activeProfile && (
          <span className="mt-2 text-xs" style={{ color: 'var(--theme-accent)' }}>
            {activeProfile.name}
            {activeProfile.model ? ` · ${activeProfile.model}` : ''}
          </span>
        )}

        {!compact && (
          <>
            <p className="mt-3 text-sm" style={{ color: 'var(--theme-muted)' }}>
              Agent chat · live tools · memory · full observability
            </p>
          </>
        )}

        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion.label}
              type="button"
              onClick={() => onSuggestionClick?.(suggestion.prompt)}
              className="flex cursor-pointer items-center gap-2 rounded-md px-3.5 py-2 text-xs font-medium transition-all"
              style={{
                background: 'var(--theme-card)',
                border: '1px solid var(--theme-border)',
                color: 'var(--theme-text)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--theme-card2)'
                e.currentTarget.style.borderColor = 'var(--theme-accent-border)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'var(--theme-card)'
                e.currentTarget.style.borderColor = 'var(--theme-border)'
              }}
            >
              <suggestion.icon
                className="size-3.5"
                style={{ color: 'var(--theme-accent)' }}
              />
              {suggestion.label}
            </button>
          ))}
        </div>
      </div>
    </motion.div>
  )
}
