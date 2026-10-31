import Image from 'next/image'

/** Palawan Collective brand mark (white-label base: swap /brand/logo-*.png to rebrand). */
export function Logo({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <Image
        src="/brand/logo-light.png"
        alt="Palawan Collective"
        width={128}
        height={63}
        className="h-9 w-auto dark:hidden"
        priority
      />
      <Image
        src="/brand/logo-dark.png"
        alt="Palawan Collective"
        width={128}
        height={63}
        className="hidden h-9 w-auto dark:block"
        priority
      />
    </span>
  )
}
