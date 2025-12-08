"use client"

import { useEffect } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useAuth } from "@/lib/auth"

export default function AuthCallbackPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { refreshUser } = useAuth()

  useEffect(() => {
    const token = searchParams.get("token")

    if (token) {
      // Store the session token
      localStorage.setItem("session_token", token)

      // Refresh user data
      refreshUser().then(() => {
        router.push("/dashboard")
      })
    } else {
      // No token, redirect to home
      router.push("/")
    }
  }, [searchParams, router, refreshUser])

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
        <p className="text-muted-foreground">Signing you in...</p>
      </div>
    </div>
  )
}
