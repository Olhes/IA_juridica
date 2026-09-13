'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { authService, type AuthState, type User } from '../../application/legal/services/authService';

interface AuthContextType extends AuthState {
  mounted: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (data: { email: string; username: string; password: string; full_name?: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    user: null,
    token: null,
  });
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);

    // Suscribirse a cambios en authService
    const unsubscribe = authService.subscribe((state) => {
      setAuthState(state);
    });

    // Intentar auto-login solo una vez al montar
    const autoLogin = async () => {
      try {
        console.log('🔍 Verificando autenticación con cookies...');
        const user = await authService.getCurrentUser();
        if (user) {
          console.log('✅ Usuario autenticado:', user.email);
          authService.setState({
            isAuthenticated: true,
            user,
            token: 'from_cookie',
          });
          // Limpiar el flag
          localStorage.removeItem('auth_just_logged_in');
        } else {
          console.log('❌ No hay usuario autenticado');
        }
      } catch (error) {
        // No autenticado, continuar sin login
        console.log('❌ No autenticado o sesión expirada:', error);
      }
    };

    autoLogin();

    // Escuchar cambios en localStorage para re-verificar después del callback
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'auth_just_logged_in' && e.newValue === 'true') {
        console.log('🔄 Usuario acaba de hacer login, re-verificando...');
        autoLogin();
      }
    };

    window.addEventListener('storage', handleStorageChange);

    // También verificar si el flag ya existe (para el caso de navegación en la misma pestaña)
    if (localStorage.getItem('auth_just_logged_in') === 'true') {
      console.log('🔄 Flag de login detectado, re-verificando...');
      autoLogin();
    }

    return () => {
      unsubscribe();
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  const login = async (username: string, password: string) => {
    await authService.login({ username, password });
  };

  const register = async (data: { email: string; username: string; password: string; full_name?: string }) => {
    await authService.register(data);
  };

  const logout = async () => {
    await authService.logout();
  };

  const refreshUser = async () => {
    const user = await authService.getCurrentUser();
    if (user) {
      setAuthState(prev => ({
        ...prev,
        user,
      }));
    }
  };

  if (!mounted) {
    return null; // Evitar hydration mismatch
  }

  return (
    <AuthContext.Provider
      value={{
        ...authState,
        mounted,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
