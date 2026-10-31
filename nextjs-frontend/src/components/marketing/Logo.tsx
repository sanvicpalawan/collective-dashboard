import Image from 'next/image'

/** MerQato Digital brand: Palawan Collective turtle mark + MerQato Digital wordmark. */
export function Logo({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <Image
        src="/brand/mark-light.png"
        alt=""
        width={44}
        height={44}
        className="h-8 w-8 dark:hidden"
        priority
      />
      <Image
        src="/brand/mark-dark.png"
        alt=""
        width={44}
        height={44}
        className="hidden h-8 w-8 dark:block"
        priority
      />
      <span className="font-display text-[22px] font-semibold tracking-[-0.03em]">MerQato Digital</span>
    </span>
  )
}
