import { createContext, useContext, useState, useCallback } from 'react'
import { cn } from '@/lib/utils'

interface CollapsibleContextValue {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const CollapsibleContext = createContext<CollapsibleContextValue>({
  open: false,
  onOpenChange: () => {},
})

interface CollapsibleProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  defaultOpen?: boolean
  children: React.ReactNode
  className?: string
}

function Collapsible({
  open: controlledOpen,
  onOpenChange,
  defaultOpen = false,
  children,
  className,
}: CollapsibleProps) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen)

  const open = controlledOpen ?? internalOpen

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (controlledOpen === undefined) {
        setInternalOpen(next)
      }
      onOpenChange?.(next)
    },
    [controlledOpen, onOpenChange],
  )

  return (
    <CollapsibleContext.Provider value={{ open, onOpenChange: handleOpenChange }}>
      <div className={className}>{children}</div>
    </CollapsibleContext.Provider>
  )
}

function useCollapsibleContext() {
  const ctx = useContext(CollapsibleContext)
  if (!ctx) {
    throw new Error(
      'Collapsible compound components must be used within a Collapsible wrapper',
    )
  }
  return ctx
}

interface CollapsibleTriggerProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode
  className?: string
}

function CollapsibleTrigger({
  className,
  children,
  ...props
}: CollapsibleTriggerProps) {
  const { open, onOpenChange } = useCollapsibleContext()

  return (
    <button
      type="button"
      data-panel-open={open ? '' : undefined}
      className={cn(
        'group inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs font-medium text-[var(--theme-muted)] transition-colors hover:bg-[var(--theme-card2)] hover:text-[var(--theme-text)] data-panel-open:text-[var(--theme-text)]',
        className,
      )}
      onClick={() => onOpenChange(!open)}
      {...props}
    >
      {children}
    </button>
  )
}

interface CollapsiblePanelProps
  extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  contentClassName?: string
  className?: string
  /** Whether to keep the panel content mounted when collapsed */
  keepMounted?: boolean
}

function CollapsiblePanel({
  className,
  contentClassName,
  children,
  keepMounted = true,
  ...props
}: CollapsiblePanelProps) {
  const { open } = useCollapsibleContext()
  const [mounted, setMounted] = useState(open)

  // Keep mounted once opened if keepMounted is true
  if (open) setMounted(true)

  const shouldRender = open || (keepMounted && mounted)

  if (!shouldRender) return null

  return (
    <div
      data-ending-style={open ? undefined : ''}
      data-starting-style={!open ? '' : undefined}
      className={cn(
        'flex h-(--collapsible-panel-height) flex-col overflow-hidden text-sm transition-all duration-150 ease-out data-ending-style:h-0 data-starting-style:h-0',
        className,
      )}
      {...props}
    >
      <div className={cn('pt-1', contentClassName)}>{children}</div>
    </div>
  )
}

export default { Collapsible, CollapsibleTrigger, CollapsiblePanel }
export { Collapsible, CollapsibleTrigger, CollapsiblePanel }
