export async function fetchIncidents() {
  const response = await fetch('/api/v1/events')
  return response.json()
}

export async function fetchDashboardSummary() {
  const response = await fetch('/api/v1/dashboard/summary')
  return response.json()
}

export async function fetchCameraSources() {
  const response = await fetch('/api/v1/cameras')
  return response.json()
}

export async function startCameraAnalysis(cameraId) {
  const response = await fetch(`/api/v1/videos/analyze/${cameraId}`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error(`Failed to start analysis for ${cameraId} (${response.status})`)
  }

  return response.json()
}

export async function fetchRun(runId) {
  if (runId == null) {
    throw new Error('runId is required')
  }

  const response = await fetch(`/api/v1/runs/${runId}`)

  if (!response.ok) {
    throw new Error(`Failed to fetch run ${runId} (${response.status})`)
  }

  return response.json()
}

export async function fetchRunEvents(runId) {
  if (runId == null || runId === 'undefined') {
    return []
  }

  const response = await fetch(`/api/v1/events?run_id=${encodeURIComponent(runId)}`)

  if (!response.ok) {
    throw new Error(`Failed to fetch events for run ${runId} (${response.status})`)
  }

  return response.json()
}
