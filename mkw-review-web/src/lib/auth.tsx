"use client"

import React, { createContext, useContext, useEffect, useState } from "react"
import { api, User, Guild } from "./api"

interface AuthContextType {
  user: User | null
  guilds: Guild[]
  selectedGuild: Guild | null
  isLoading: boolean
  isAuthenticated: boolean
  login: () => void
  logout: () => void
  selectGuild: (guild: Guild) => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [guilds, setGuilds] = useState<Guild[]>([])
  const [selectedGuild, setSelectedGuild] = useState<Guild | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const refreshUser = async () => {
    try {
      const token = localStorage.getItem("session_token")
      if (!token) {
        setUser(null)
        setGuilds([])
        return
      }

      const userData = await api.getCurrentUser(token)
      if (userData) {
        setUser(userData)

        // Convert guild permissions to Guild array
        const guildList: Guild[] = Object.entries(userData.guilds || {}).map(
          ([id, perms]: [string, any]) => ({
            id,
            name: perms.guild_name || `Guild ${id}`,
            is_admin: perms.is_admin || false,
            can_manage: perms.can_manage || false,
            is_configured: true
          })
        )
        setGuilds(guildList)

        // Auto-select first guild if none selected
        if (!selectedGuild && guildList.length > 0) {
          setSelectedGuild(guildList[0])
        }
      }
    } catch (error) {
      console.error("Failed to refresh user:", error)
      setUser(null)
      setGuilds([])
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    refreshUser()
  }, [])

  const login = () => {
    window.location.href = api.getLoginUrl()
  }

  const logout = async () => {
    const token = localStorage.getItem("session_token")
    if (token) {
      await api.logout(token)
    }
    localStorage.removeItem("session_token")
    setUser(null)
    setGuilds([])
    setSelectedGuild(null)
  }

  const selectGuild = (guild: Guild) => {
    setSelectedGuild(guild)
    localStorage.setItem("selected_guild", guild.id)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        guilds,
        selectedGuild,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        selectGuild,
        refreshUser
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}
