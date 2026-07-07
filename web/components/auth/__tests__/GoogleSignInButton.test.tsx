import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { GoogleSignInButton } from '@/components/auth/GoogleSignInButton'

afterEach(() => vi.unstubAllEnvs())

describe('GoogleSignInButton', () => {
  it('não renderiza nada sem NEXT_PUBLIC_GOOGLE_CLIENT_ID', () => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_CLIENT_ID', '')
    const { container } = render(<GoogleSignInButton onCredential={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renderiza o container do botão quando o client id existe', () => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_CLIENT_ID', 'cid-test')
    const { getByTestId } = render(<GoogleSignInButton onCredential={() => {}} />)
    expect(getByTestId('google-signin')).toBeInTheDocument()
  })
})
