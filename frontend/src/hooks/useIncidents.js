import { useEffect, useState } from 'react'
import { fetchIncidents } from '../services/api'

export function useIncidents() {
  const [incidents, setIncidents] = useState([])

  useEffect(() => {
    fetchIncidents().then(setIncidents).catch(() => setIncidents([]))
  }, [])

  return incidents
}
