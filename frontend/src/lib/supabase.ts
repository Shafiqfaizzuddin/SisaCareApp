import { createClient } from '@supabase/supabase-js'

const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL as string | undefined)?.trim()
const supabasePublishableKey = (
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined
)?.trim()

export const supabaseClient =
  supabaseUrl && supabasePublishableKey
    ? (() => {
        const oldKey = `sb-${new URL(supabaseUrl).hostname.split('.')[0]}-auth-token`
        window.localStorage.removeItem(oldKey)
        return createClient(supabaseUrl, supabasePublishableKey, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
          storage: window.sessionStorage,
          storageKey: 'sisacare-browser-session',
        },
      })
      })()
    : null
