import Image from 'next/image'

/**
 * MerQato Digital brand: Palawan Collective turtle mark + MerQato Digital wordmark.
 * `compact` is for tight chrome (the sidebar) where the wordmark must fit on one line.
 */
export function Logo({ className = '', compact = false }: { className?: string; compact?: boolean }) {
  const mark = compact ? 'h-7 w-7' : 'h-8 w-8'
  const text = compact ? 'text-[17px]' : 'text-[22px]'
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <Image
        src="/brand/mark-light.png"
        alt=""
        width={44}
        height={44}
        className={`${mark} flex-shrink-0 dark:hidden`}
        priority
      />
      <Image
        src="/brand/mark-dark.png"
        alt=""
        width={44}
        height={44}
        className={`${mark} hidden flex-shrink-0 dark:block`}
        priority
      />
      <span className={`whitespace-nowrap font-display ${text} font-semibold tracking-[-0.03em]`}>
        MerQato Digital
      </span>
    </span>
  )
}
