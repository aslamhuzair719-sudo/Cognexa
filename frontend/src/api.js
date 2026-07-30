async function parseResponse(response) {
  const raw = await response.text()
  let data = {}
  try {
    data = raw ? JSON.parse(raw) : {}
  } catch {
    throw new Error(raw.slice(0, 280) || `HTTP ${response.status}`)
  }
  if (!response.ok) {
    const detail = data.detail
    if (typeof detail === 'string') throw new Error(detail)
    if (Array.isArray(detail)) {
      throw new Error(
        detail
          .map((item) => {
            const loc = Array.isArray(item.loc)
              ? item.loc.filter((p) => p !== 'body').join('.')
              : ''
            return loc ? `${loc}: ${item.msg}` : item.msg || JSON.stringify(item)
          })
          .join('; '),
      )
    }
    throw new Error(JSON.stringify(data) || `HTTP ${response.status}`)
  }
  return data
}

export async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...options,
  })
  return parseResponse(response)
}

export function downloadUrl(path) {
  // Opens authenticated download in same origin (session cookie).
  window.location.href = path
}
