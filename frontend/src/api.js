const BASE_URL = import.meta.env.VITE_API_URL || ''

export async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.adminKey ? { 'X-Admin-Key': options.adminKey } : {}),
      ...(options.headers || {})
    }
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = body.detail
    const message = Array.isArray(detail) ? detail.map(item => `${item.loc?.join('.')}: ${item.msg}`).join('; ') : detail
    throw new Error(message || `${response.status} ${response.statusText}`)
  }
  return body
}

export const getNetwork = () => request('/api/network')
export const getReports = () => request('/api/reports')
export const getEvaluations = () => request('/api/evaluations')
export const calculateRoute = (params, signal) => request('/api/routes', {
  method: 'POST', body: JSON.stringify(params), signal
})
export const submitReport = (params) => request('/api/reports', {
  method: 'POST', body: JSON.stringify(params)
})
export const moderateReport = (id, action, note, adminKey) => request(`/api/admin/reports/${id}/moderate`, {
  method: 'POST', body: JSON.stringify({ action, note }), adminKey
})
export const getAdminOverview = (adminKey) => request('/api/admin/overview', { adminKey })
export const runBenchmark = (adminKey) => request('/api/evaluations/run', { method: 'POST', adminKey })
