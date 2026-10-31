import Image from 'next/image'

/** MerQato Digital mark + wordmark. Placeholder logo image; replace /logo.svg with branded asset. */
export function Logo({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <Image src="/logo.svg" alt="MerQato Digital" width={30} height={30} className="dark:invert" priority />
      <span className="font-display text-[26px] font-semibold tracking-[-0.04em]">MerQato Digital</span>
    </span>
  )
}
