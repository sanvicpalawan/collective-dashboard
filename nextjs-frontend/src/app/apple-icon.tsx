import { ImageResponse } from 'next/og'

// Square home-screen / bookmark icon, drawn from the Palawan Collective brand color.
export const size = { width: 180, height: 180 }
export const contentType = 'image/png'

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #91a0ff, #6374e6)',
          color: '#0c0d10',
          fontSize: 96,
          fontWeight: 800,
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        PC
      </div>
    ),
    { ...size },
  )
}
