import { authHeaders, clearAuth } from './auth'

async function request(path, params = {}) {
  const url = new URL(path, window.location.origin)
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      url.searchParams.set(k, String(v))
    }
  })
  const resp = await fetch(url.pathname + url.search, {
    headers: authHeaders(),
  })
  const body = await resp.json().catch(() => ({}))
  if (resp.status === 401 || body.code === 401) {
    clearAuth()
    window.dispatchEvent(new CustomEvent('auth:logout'))
    throw new Error(body.message || '未登录')
  }
  if (!resp.ok || body.code !== 200) {
    throw new Error(body.message || body.detail || `请求失败 ${resp.status}`)
  }
  return body.data
}

export function fetchHealth() {
  // health stays public
  return fetch('/api/v1/health').then(async (resp) => {
    const body = await resp.json()
    if (!resp.ok || body.code !== 200) {
      throw new Error(body.message || `请求失败 ${resp.status}`)
    }
    return body.data
  })
}

export function fetchOverview(startDate, endDate, gameId) {
  return request('/api/v1/dashboard/overview', {
    start_date: startDate,
    end_date: endDate,
    game_id: gameId,
  })
}

export function fetchTrends(metric, startDate, endDate, gameId) {
  return request('/api/v1/dashboard/trends', {
    metric,
    start_date: startDate,
    end_date: endDate,
    game_id: gameId,
  })
}

export function fetchGameRank(metric, startDate, endDate, limit = 8) {
  return request('/api/v1/dashboard/game-rank', {
    metric,
    start_date: startDate,
    end_date: endDate,
    limit,
  })
}

export function fetchGameDetail(gameId, startDate, endDate) {
  return request(`/api/v1/dashboard/games/${gameId}`, {
    start_date: startDate,
    end_date: endDate,
  })
}
