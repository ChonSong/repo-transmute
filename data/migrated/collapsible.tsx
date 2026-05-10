import * as React from 'react'
import { cn } from '@/lib/utils'

interface CollapsibleContextType {
  open: boolean
  setOpen: (open: boolean) => void
}

const CollapsibleContext = React.createContext<CollapsibleContextType | null>(null)

function useCollapsibleContext() {
  const ctx = React.useContext(CollapsibleContext)
  if (!ctx) throw new Error('Collapsible compound components must be rendered within <Collapsible>')
  return ctx
}

interface CollapsibleProps {
  children: React.ReactNode
  className?: string
  open?: boolean
  defaultOpen?: boolean
  onOpenChange?: (open: boolean) => void
}

function Collapsible({
  children,
  className,
  open: controlledOpen,
  defaultOpen = false,
  onOpenChange,
}: CollapsibleProps) {
  const [internalOpen, setInternalOpen] = React.useState(defaultOpen)
  const open = controlledOpen ?? internalOpen

  const setOpen = React.useCallback(
    (val: boolean) => {
      setInternalOpen(val)
      onOpenChange?.(val)
    },
    [onOpenChange],
  )

  return (
    <CollapsibleContext.Provider value={{ open, setOpen }}>
      <div className={className}>{children}</div>
    </CollapsibleContext.Provider>
  )
}

interface CollapsibleTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  className?: string
}

function CollapsibleTrigger({ className, children, onClick, ...props }: CollapsibleTriggerProps) {
  const { open, setOpen } = useCollapsibleContext()

  return (
    <button
      type="button"
      className={cn(
        'group inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs font-medium text-[var(--theme-muted)] transition-colors hover:bg-[var(--theme-card2)] hover:text-[var(--theme-text)]',
        open && 'text-[var(--theme-text)]',
        className,
      )}
      onClick={(e) => {
        setOpen(!open)
        onClick?.(e)
      }}
      data-panel-open={open ? '' : undefined}
      {...props}
    >
      {children}
    </button>
  )
}

interface CollapsiblePanelProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string
  contentClassName?: string
  children: React.ReactNode
}

function CollapsiblePanel({
  className,
  contentClassName,
  children,
  ...props
}: CollapsiblePanelProps) {
  const { open } = useCollapsibleContext()

  return (
    <div
      className={cn(
        'flex flex-col overflow-hidden text-sm transition-all duration-150 ease-out',
        !open && 'h-0',
        className,
      )}
      data-ending-style={!open ? '' : undefined}
      style={{ height: open ? undefined : 0 }}
      {...props}
    >
      <div className={cn('pt-1', contentClassName)}>{children}</div>
    </div>
  )
}

export default { Collapsible, CollapsibleTrigger, CollapsiblePanel }
export { Collapsible, CollapsibleTrigger, CollapsiblePanel }
