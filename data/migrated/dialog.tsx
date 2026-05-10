import * as React from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/utils'

interface DialogContextType {
  open: boolean
  setOpen: (open: boolean) => void
}

const DialogContext = React.createContext<DialogContextType | null>(null)

function useDialogContext() {
  const ctx = React.useContext(DialogContext)
  if (!ctx) throw new Error('Dialog compound components must be rendered within <DialogRoot>')
  return ctx
}

interface DialogRootProps {
  children: React.ReactNode
  open?: boolean
  defaultOpen?: boolean
  onOpenChange?: (open: boolean) => void
}

function DialogRoot({ children, open: controlledOpen, defaultOpen = false, onOpenChange }: DialogRootProps) {
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
    <DialogContext.Provider value={{ open, setOpen }}>
      {children}
    </DialogContext.Provider>
  )
}

interface DialogTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  className?: string
  children: React.ReactNode
}

function DialogTrigger({ className, children, onClick, ...props }: DialogTriggerProps) {
  const { setOpen } = useDialogContext()

  return (
    <button
      type="button"
      className={cn(className)}
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

interface DialogContentProps {
  className?: string
  children: React.ReactNode
  style?: React.CSSProperties
}

function DialogContent({ className, children, style }: DialogContentProps) {
  const { open, setOpen } = useDialogContext()

  React.useEffect(() => {
    if (!open) return
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [open, setOpen])

  if (!open) return null

  return createPortal(
    <>
      <div
        className="fixed inset-0 transition-all duration-150"
        style={{ background: 'rgba(0,0,0,0.5)' }}
        onClick={() => setOpen(false)}
      />
      <div
        className={cn(
          'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2',
          'w-[min(400px,92vw)] max-h-[90vh] rounded-[10px] p-0 overflow-hidden flex flex-col',
          'transition-all duration-150',
          className,
        )}
        style={{
          background: 'var(--theme-panel)',
          border: '1px solid var(--theme-border)',
          boxShadow: 'var(--theme-shadow-3)',
          color: 'var(--theme-text)',
          ...style,
        }}
        role="dialog"
        aria-modal="true"
      >
        {children}
      </div>
    </>,
    document.body,
  )
}

interface DialogTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {
  className?: string
  children: React.ReactNode
}

function DialogTitle({ className, children, ...props }: DialogTitleProps) {
  return (
    <h2
      className={cn('text-lg font-medium', className)}
      style={{ color: 'var(--theme-text)' }}
      {...props}
    >
      {children}
    </h2>
  )
}

interface DialogDescriptionProps extends React.HTMLAttributes<HTMLParagraphElement> {
  className?: string
  children: React.ReactNode
}

function DialogDescription({ className, children, ...props }: DialogDescriptionProps) {
  return (
    <p
      className={cn('text-sm', className)}
      style={{ color: 'var(--theme-muted)' }}
      {...props}
    >
      {children}
    </p>
  )
}

interface DialogCloseProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  className?: string
  children?: React.ReactNode
}

function DialogClose({ className, children, onClick, ...props }: DialogCloseProps) {
  const { setOpen } = useDialogContext()

  return (
    <button
      type="button"
      className={cn(className)}
      onClick={(e) => {
        setOpen(false)
        onClick?.(e)
      }}
      {...props}
    >
      {children}
    </button>
  )
}

export default { DialogRoot, DialogTrigger, DialogContent, DialogTitle, DialogDescription, DialogClose }
export { DialogRoot, DialogTrigger, DialogContent, DialogTitle, DialogDescription, DialogClose }
