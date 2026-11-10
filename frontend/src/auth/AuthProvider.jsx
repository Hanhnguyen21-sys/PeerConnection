import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { supabase } from '../lib/supabase'
import { fetchMe } from '../lib/api'
import { AuthContext } from './AuthContext'

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [isRestoring, setIsRestoring] = useState(true)
  const [profileResult, setProfileResult] = useState(null)
  const [reloadCount, setReloadCount] = useState(0)

  // Restores the saved session on load (INITIAL_SESSION) and tracks later changes.
  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      // Keep this callback synchronous; awaiting Supabase calls here can deadlock the client.
      setSession(nextSession)
      setIsRestoring(false)
    })
    return () => subscription.unsubscribe()
  }, [])

  const userId = session?.user?.id ?? null
  const accessToken = session?.access_token ?? null

  // Token refreshes shouldn't refetch the profile, so read the latest token through a ref.
  const accessTokenRef = useRef(accessToken)
  useEffect(() => {
    accessTokenRef.current = accessToken
  }, [accessToken])

  const profileKey = userId ? `${userId}:${reloadCount}` : null

  useEffect(() => {
    if (!profileKey) return
    const controller = new AbortController()
    fetchMe(accessTokenRef.current, { signal: controller.signal })
      .then((profile) => setProfileResult({ key: profileKey, profile, error: null }))
      .catch((error) => {
        if (error.name === 'AbortError') return
        setProfileResult({ key: profileKey, profile: null, error })
      })
    return () => controller.abort()
  }, [profileKey])

  const currentProfile = profileResult?.key === profileKey ? profileResult : null

  const reloadProfile = useCallback(() => setReloadCount((count) => count + 1), [])

  const signOut = useCallback(async () => {
    const { error } = await supabase.auth.signOut()
    if (error) throw error
  }, [])

  const value = useMemo(
    () => ({
      session,
      isRestoring,
      profile: currentProfile?.profile ?? null,
      profileError: currentProfile?.error ?? null,
      isProfileLoading: Boolean(profileKey) && !currentProfile,
      reloadProfile,
      signOut,
    }),
    [session, isRestoring, currentProfile, profileKey, reloadProfile, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
