const TOKEN_KEY = 'game_ops_token'
const USER_KEY = 'game_ops_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token || '')
  localStorage.setItem(USER_KEY, JSON.stringify(user || null))
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function authHeaders(extra = {}) {
  const token = getToken()
  const headers = { ...extra }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

export async function login(username, password) {
  const resp = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const payload = await resp.json()
  if (!resp.ok || payload.code !== 200) {
    throw new Error(payload.message || '登录失败')
  }
  setAuth(payload.data.access_token, payload.data.user)
  return payload.data
}

export async function fetchMe() {
  const resp = await fetch('/api/v1/auth/me', { headers: authHeaders() })
  const payload = await resp.json()
  if (resp.status === 401 || payload.code === 401) {
    clearAuth()
    throw new Error(payload.message || '未登录')
  }
  if (!resp.ok || payload.code !== 200) {
    throw new Error(payload.message || '获取用户失败')
  }
  setAuth(getToken(), payload.data)
  return payload.data
}

export async function logout() {
  try {
    await fetch('/api/v1/auth/logout', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
    })
  } catch {
    /* ignore */
  }
  clearAuth()
}
