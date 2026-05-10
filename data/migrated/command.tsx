import * as React from 'react'
import { Search } from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Command Dialog ────────────────────────────────────────────────

interface CommandDialogContextType {
  open: boolean
  setOpen: (open: boolean) => void
}

const CommandDialogContext = React.createContext<CommandDialogContextType | null>(null)

function useCommandDialogContext() {
  const ctx = React.useContext(CommandDialogContext)
  if (!ctx) throw new Error('CommandDialog compound components must be rendered within <CommandDialogRoot>')
  return ctx
}

interface CommandDialogRootProps {
  children: React.ReactNode
  open?: boolean
  defaultOpen?: boolean
  onOpenChange?: (open: boolean) => void
}

function CommandDialogRoot({ children, open: controlledOpen, defaultOpen = false, onOpenChange }: CommandDialogRootProps) {
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
    <CommandDialogContext.Provider value={{ open, setOpen }}>
      {children}
    </CommandDialogContext.Provider>
  )
}

function CommandDialogTrigger({
  className,
  children,
  onClick,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { children: React.ReactNode }) {
  const { setOpen } = useCommandDialogContext()

  return (
    <button
      type="button"
      data-slot="command-dialog-trigger"
      className={className}
      onClick={(e) => {
        setOpen(true)
        onClick?.(e)
      }}
      {...props}
    >
      {children}
    </button>
  )
}

function CommandDialogBackdrop({
  className,
  onClick,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const { setOpen } = useCommandDialogContext()

  return (
    <div
      className={cn(
        'fixed inset-0 z-50 bg-black/40 backdrop-blur-sm transition-all duration-200',
        className,
      )}
      data-slot="command-dialog-backdrop"
      onClick={() => {
        setOpen(false)
        onClick?.(undefined as any)
      }}
      {...props}
    />
  )
}

function CommandDialogViewport({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'fixed inset-0 z-50 flex flex-col items-center justify-center px-4 py-[max(1rem,4vh)]',
        className,
      )}
      data-slot="command-dialog-viewport"
      {...props}
    >
      {children}
    </div>
  )
}

function CommandDialogPopup({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const { open } = useCommandDialogContext()

  if (!open) return null

  return (
    <>
      <CommandDialogBackdrop />
      <CommandDialogViewport>
        <div
          className={cn(
            'relative row-start-2 flex max-h-105 min-h-0 w-full min-w-0 max-w-xl flex-col rounded-2xl shadow-lg outline-1 outline-primary-950/10 outline transition-[scale,opacity,translate] duration-200 ease-in-out will-change-transform',
            className,
          )}
          data-slot="command-dialog-popup"
          style={{
            background: 'var(--theme-card)',
            color: 'var(--theme-text)',
            border: '1px solid var(--theme-border)',
          }}
          role="dialog"
          aria-modal="true"
          {...props}
        >
          {children}
        </div>
      </CommandDialogViewport>
    </>
  )
}

// ── Command ───────────────────────────────────────────────────────

interface CommandOption {
  id: string
  label: string
  value?: string
  group?: string
  shortcut?: string
  icon?: React.ReactNode
  onSelect?: () => void
}

interface CommandGroup {
  id: string
  label?: string
  items: CommandOption[]
}

interface CommandProps {
  children: React.ReactNode
  className?: string
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
}

const CommandContext = React.createContext<{
  filter: string
  setFilter: (v: string) => void
  highlightedIndex: number
  setHighlightedIndex: (v: number) => void
  filteredOptions: CommandOption[]
  registerOption: (opt: CommandOption) => void
  unregisterOption: (id: string) => void
} | null>(null)

function useCommandContext() {
  const ctx = React.useContext(CommandContext)
  if (!ctx) throw new Error('Command compound components must be rendered within <Command>')
  return ctx
}

function Command({
  children,
  className,
  value,
  defaultValue = '',
  onValueChange,
}: CommandProps) {
  const [internalValue, setInternalValue] = React.useState(defaultValue)
  const filter = value ?? internalValue
  const [highlightedIndex, setHighlightedIndex] = React.useState(0)
  const [options, setOptions] = React.useState<CommandOption[]>([])

  const setFilter = React.useCallback(
    (v: string) => {
      setInternalValue(v)
      onValueChange?.(v)
    },
    [onValueChange],
  )

  const filteredOptions = React.useMemo(() => {
    if (!filter) return options
    const lower = filter.toLowerCase()
    return options.filter(
      (o) =>
        o.label.toLowerCase().includes(lower) ||
        (o.value && o.value.toLowerCase().includes(lower)),
    )
  }, [options, filter])

  const registerOption = React.useCallback((opt: CommandOption) => {
    setOptions((prev) => [...prev, opt])
  }, [])

  const unregisterOption = React.useCallback((id: string) => {
    setOptions((prev) => prev.filter((o) => o.id !== id))
  }, [])

  return (
    <CommandContext.Provider
      value={{
        filter,
        setFilter,
        highlightedIndex,
        setHighlightedIndex,
        filteredOptions,
        registerOption,
        unregisterOption,
      }}
    >
      <div
        className={cn('flex flex-col', className)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setHighlightedIndex((prev) =>
              Math.min(prev + 1, filteredOptions.length - 1),
            )
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setHighlightedIndex((prev) => Math.max(prev - 1, 0))
          } else if (e.key === 'Enter') {
            e.preventDefault()
            filteredOptions[highlightedIndex]?.onSelect?.()
          }
        }}
      >
        {children}
      </div>
    </CommandContext.Provider>
  )
}

// ── Command Input ─────────────────────────────────────────────────

interface CommandInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  className?: string
  placeholder?: string
}

function CommandInput({ className, placeholder = 'Type a command or search...', ...props }: CommandInputProps) {
  const { filter, setFilter } = useCommandContext()

  return (
    <div className="px-2.5 py-1.5 flex items-center gap-2">
      <Search size={20} strokeWidth={1.5} className="shrink-0 text-muted-foreground" />
      <input
        autoFocus
        type="text"
        className={cn(
          'flex-1 border-transparent bg-transparent shadow-none outline-none focus-visible:ring-0 text-sm',
          className,
        )}
        placeholder={placeholder}
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        {...props}
      />
    </div>
  )
}

// ── Command List ──────────────────────────────────────────────────

function CommandList({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('overflow-y-auto p-2 scroll-py-2', className)}
      data-slot="command-list"
      {...props}
    >
      {children}
    </div>
  )
}

// ── Command Empty ─────────────────────────────────────────────────

function CommandEmpty({
  className,
  children = 'No results found.',
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const { filteredOptions } = useCommandContext()

  if (filteredOptions.length > 0) return null

  return (
    <div
      className={cn('py-6 text-center text-sm text-muted-foreground', className)}
      data-slot="command-empty"
      {...props}
    >
      {children}
    </div>
  )
}

// ── Command Panel ─────────────────────────────────────────────────

function CommandPanel({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'relative min-h-0 rounded-t-xl border border-b-0 bg-clip-padding shadow-xs/5',
        className,
      )}
      style={{
        background: 'var(--theme-card)',
        borderColor: 'var(--theme-border)',
      }}
      {...props}
    >
      {children}
    </div>
  )
}

// ── Command Group ─────────────────────────────────────────────────

function CommandGroup({
  className,
  children,
  heading,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { heading?: string }) {
  return (
    <div
      className={className}
      data-slot="command-group"
      {...props}
    >
      {heading && (
        <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
          {heading}
        </div>
      )}
      {children}
    </div>
  )
}

// ── Command Item ──────────────────────────────────────────────────

interface CommandItemProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string
  value?: string
  onSelect?: () => void
  disabled?: boolean
}

function CommandItem({
  className,
  children,
  value,
  onSelect,
  disabled,
  ...props
}: CommandItemProps) {
  const { filteredOptions, highlightedIndex } = useCommandContext()
  const ref = React.useRef<HTMLDivElement>(null)
  const id = React.useId()

  const index = filteredOptions.findIndex((o) => o.id === id || o.value === value)
  const isHighlighted = index === highlightedIndex

  React.useEffect(() => {
    if (isHighlighted && ref.current) {
      ref.current.scrollIntoView({ block: 'nearest' })
    }
  }, [isHighlighted])

  return (
    <div
      ref={ref}
      role="option"
      aria-selected={isHighlighted}
      className={cn(
        'relative flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none transition-colors',
        isHighlighted && 'bg-accent text-accent-foreground',
        disabled && 'pointer-events-none opacity-50',
        className,
      )}
      data-slot="command-item"
      onClick={() => {
        if (!disabled) onSelect?.()
      }}
      {...props}
    >
      {children}
    </div>
  )
}

// ── Command Separator ─────────────────────────────────────────────

function CommandSeparator({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('my-2 h-px bg-border', className)}
      data-slot="command-separator"
      {...props}
    />
  )
}

// ── Command Shortcut ──────────────────────────────────────────────

function CommandShortcut({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'ms-auto font-medium font-sans text-xs tracking-widest',
        className,
      )}
      data-slot="command-shortcut"
      style={{ color: 'var(--theme-muted)' }}
      {...props}
    />
  )
}

// ── Command Footer ────────────────────────────────────────────────

function CommandFooter({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'flex items-center justify-between gap-2 rounded-b-xl border-t px-5 py-3 text-xs',
        className,
      )}
      data-slot="command-footer"
      style={{
        borderColor: 'var(--theme-border)',
        color: 'var(--theme-muted)',
      }}
      {...props}
    >
      {children}
    </div>
  )
}

export default Command
export {
  Command,
  CommandDialogRoot as CommandDialog,
  CommandDialogPopup,
  CommandDialogTrigger,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandPanel,
  CommandGroup,
  CommandItem,
  CommandSeparator,
  CommandShortcut,
  CommandFooter,
}
