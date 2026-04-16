export async function fetchIncidents() {
  const response = await fetch('/api/v1/events')
  return response.json()
}

export async function fetchDashboardSummary() {
  const response = await fetch('/api/v1/dashboard/summary')
  return response.json()
}

export async function uploadVideo(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch('/api/v1/videos/upload', {
    method: 'POST',
    body: formData,
  })

  return response.json()
}
