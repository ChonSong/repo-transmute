import * as React from 'react'
import { cn } from '@/lib/utils'

interface SwitchProps extends React.InputHTMLAttributes<HTMLButtonElement> {
  className?: string
  checked?: boolean
  defaultChecked?: boolean
  onCheckedChange?: (checked: boolean) => void
  disabled?: boolean
}

function Switch({
  className,
  checked: controlledChecked,
  defaultChecked = false,
  onCheckedChange,
  disabled,
  ...props
}: SwitchProps) {
  const [internalChecked, setInternalChecked] = React.useState(defaultChecked)
  const isChecked = controlledChecked ?? internalChecked

  const handleToggle = React.useCallback(() => {
    if (disabled) return
    const next = !isChecked
    setInternalChecked(next)
    onCheckedChange?.(next)
  }, [disabled, isChecked, onCheckedChange])

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isChecked}
      disabled={disabled}
      data-checked={isChecked ? 'true' : undefined}
      data-unchecked={!isChecked ? 'true' : undefined}
      data-disabled={disabled ? 'true' : undefined}
      data-slot="switch"
      className={cn(
        'relative inline-flex h-[calc(var(--thumb-size)+2px)] w-[calc(var(--thumb-size)*2.4-2px)] shrink-0 items-center rounded-full p-px outline-none transition-[background-color,box-shadow] duration-200 [--thumb-size:--spacing(5)] focus-visible:ring-2 focus-visible:ring-primary-950 focus-visible:ring-offset-1 focus-visible:ring-offset-background data-checked:bg-emerald-600 data-unchecked:bg-primary-300 dark:data-unchecked:bg-neutral-600 border border-primary-300 dark:border-neutral-500 data-checked:border-emerald-700 data-disabled:opacity-64 sm:[--thumb-size:--spacing(4)]',
        className,
      )}
      onClick={handleToggle}
      {...props}
    >
      {/* ON label — visible only when the switch is checked, on the left of
          the thumb. Tiny so it never reflows the layout, white on accent
          for contrast. */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute left-1 select-none text-[8px] font-bold uppercase tracking-wide text-white opacity-0 transition-opacity duration-150 data-checked:opacity-100"
        style={{ opacity: isChecked ? 1 : 0 }}
      >
        ON
      </span>
      {/* OFF label — visible only when the switch is unchecked, on the right
          of the thumb. Muted so it doesn't shout. */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-1 select-none text-[8px] font-bold uppercase tracking-wide text-primary-700 opacity-100 transition-opacity duration-150 dark:text-neutral-300"
        style={{ opacity: isChecked ? 0 : 1 }}
      >
        OFF
      </span>
      <span
        className={cn(
          'pointer-events-none relative z-10 block aspect-square h-full rounded-full bg-white shadow-md will-change-transform',
        )}
        style={{
          transformOrigin: isChecked
            ? 'var(--thumb-size) 50%'
            : 'left center',
          transform: isChecked
            ? 'translateX(calc(var(--thumb-size)*1.4 - 4px))'
            : 'translateX(0)',
          transition:
            'translate .15s, border-radius .15s, scale .1s .1s, transform-origin .15s',
        }}
        data-slot="switch-thumb"
      />
    </button>
  )
}

export default Switch
