import { useEffect, useState } from 'react'
import DashboardLayout from '../components/DashboardLayout'
import IncidentTable from '../components/IncidentTable'
import StatsCards from '../components/StatsCards'
import { fetchCameraSources, fetchRun, fetchRunEvents, startCameraAnalysis } from '../services/api'

const BACKEND_ORIGIN = 'http://127.0.0.1:8000'

function toAbsoluteBackendUrl(url) {
  if (!url) {
    return null
  }

  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url
  }

  if (url.startsWith('/')) {
    return `${BACKEND_ORIGIN}${url}`
  }

  return `${BACKEND_ORIGIN}/${url}`
}

function formatFps(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A'
  }

  return `${value.toFixed(2)} FPS`
}

function formatIncidentType(value) {
  if (!value) {
    return 'Unknown'
  }

  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase())
}

export default function DashboardPage() {
  const [cameraSources, setCameraSources] = useState([])
  const [cameraRuns, setCameraRuns] = useState({})
  const [cameraEvents, setCameraEvents] = useState({})
  const [cameraStatuses, setCameraStatuses] = useState({})
  const [streamFallbacks, setStreamFallbacks] = useState({})
  const [statusMessage, setStatusMessage] = useState('Loading four fixed tunnel cameras...')
  const [showGuideLines, setShowGuideLines] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function bootCameras() {
      try {
        const sources = await fetchCameraSources()
        if (cancelled) {
          return
        }

        setCameraSources(sources)
        setCameraStatuses(
          Object.fromEntries(sources.map((camera) => [camera.camera_id, 'Queued for analysis'])),
        )
        setStatusMessage('Starting analysis for Camera 1 through Camera 4...')

        const results = await Promise.allSettled(sources.map((camera) => startCameraAnalysis(camera.camera_id)))

        if (cancelled) {
          return
        }

        const nextRuns = {}
        const nextStatuses = {}
        const initialEvents = {}

        await Promise.all(
          results.map(async (result, index) => {
            const camera = sources[index]
            if (!camera) {
              return
            }

            if (result.status === 'fulfilled') {
              nextRuns[camera.camera_id] = result.value
              nextStatuses[camera.camera_id] = 'Analysis running'

              try {
                initialEvents[camera.camera_id] = await fetchRunEvents(result.value.id)
              } catch {
                initialEvents[camera.camera_id] = []
              }
            } else {
              nextStatuses[camera.camera_id] = 'Analysis unavailable'
            }
          }),
        )

        setCameraRuns(nextRuns)
        setCameraStatuses(nextStatuses)
        setCameraEvents(initialEvents)
        setStatusMessage('Four fixed camera feeds are live and being analyzed.')
      } catch {
        if (!cancelled) {
          setStatusMessage('Backend not reachable yet. Start the API service and reload the page.')
        }
      }
    }

    bootCameras()

    return () => {
      cancelled = true
    }
  }, [])

  const activeRunSignature = Object.values(cameraRuns)
    .map((run) => run.id)
    .join('|')

  useEffect(() => {
    const activeRuns = Object.entries(cameraRuns)
    if (activeRuns.length === 0) {
      return undefined
    }

    let cancelled = false

    async function refreshRuns() {
      const updates = await Promise.all(
        activeRuns.map(async ([cameraId, run]) => {
          try {
            const [latestRun, events] = await Promise.all([fetchRun(run.id), fetchRunEvents(run.id)])
            return { cameraId, latestRun, events }
          } catch {
            return { cameraId, latestRun: null, events: null }
          }
        }),
      )

      if (cancelled) {
        return
      }

      setCameraRuns((currentRuns) => {
        const nextRuns = { ...currentRuns }

        for (const update of updates) {
          if (update.latestRun) {
            nextRuns[update.cameraId] = update.latestRun
          }
        }

        return nextRuns
      })

      setCameraEvents((currentEvents) => {
        const nextEvents = { ...currentEvents }

        for (const update of updates) {
          if (Array.isArray(update.events)) {
            nextEvents[update.cameraId] = update.events
          }
        }

        return nextEvents
      })
    }

    refreshRuns().catch(() => null)
    const timer = setInterval(() => {
      refreshRuns().catch(() => null)
    }, 3000)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [activeRunSignature])

  const cameraCards = cameraSources.map((camera) => {
    const run = cameraRuns[camera.camera_id] ?? null
    const events = cameraEvents[camera.camera_id] ?? []
    const streamUrl = run
      ? `${BACKEND_ORIGIN}/api/v1/videos/analyzed/stream?run_id=${run.id}&show_lines=${showGuideLines ? 1 : 0}`
      : null
    const hasStreamFallback = streamFallbacks[camera.camera_id] ?? false

    return {
      ...camera,
      run,
      events,
      streamUrl,
      hasStreamFallback,
      sourceUrl: toAbsoluteBackendUrl(camera.source_video_url),
      status: cameraStatuses[camera.camera_id] ?? 'Queued for analysis',
    }
  })

  const flattenedEvents = cameraCards
    .flatMap((camera) =>
      camera.events.map((event) => ({
        ...event,
        camera_label: camera.label,
      })),
    )
    .sort((left, right) => right.id - left.id)

  const totals = cameraCards.reduce(
    (accumulator, camera) => {
      accumulator.totalRuns += camera.run ? 1 : 0
      accumulator.wrongWay += camera.run?.wrong_way_count ?? 0
      accumulator.stops += camera.run?.stop_count ?? 0
      accumulator.detectedEvents += camera.events.length
      return accumulator
    },
    { totalRuns: 0, wrongWay: 0, stops: 0, detectedEvents: 0 },
  )

  function handleStreamError(cameraId) {
    setStreamFallbacks((current) => ({
      ...current,
      [cameraId]: true,
    }))
    setCameraStatuses((current) => ({
      ...current,
      [cameraId]: 'Switching to source video playback',
    }))
  }

  return (
    <DashboardLayout>
      <main className="dashboard-page">
        <header className="hero-panel">
          <div>
            <p className="eyebrow">Tunnel safety operations</p>
            <h1>Four-camera tunnel incident dashboard</h1>
            <p className="lede">
              Four stored tunnel videos are wired to Camera 1 through Camera 4. Each feed starts analysis automatically and
              streams its own wrong-way and stop detections.
            </p>
          </div>
          <div className="hero-status">
            <span className="pulse" />
            {statusMessage}
          </div>
        </header>

        <section className="upload-panel">
          <div className="camera-overview">
            <div>
              <p className="eyebrow">Preset feeds</p>
              <h2>Camera 1 to Camera 4 are mapped to local video files</h2>
              <p className="upload-meta">
                No manual upload step is needed. The backend starts a detection run for each source and keeps streaming the
                processed output.
              </p>
            </div>
            <button type="button" className="line-toggle-btn" onClick={() => setShowGuideLines((value) => !value)}>
              {showGuideLines ? 'Hide guide lines' : 'Show guide lines'}
            </button>
          </div>
          <p className="upload-meta">
            Active runs: {totals.totalRuns} | Detected incidents: {totals.detectedEvents} | Source videos: {cameraCards.length}
          </p>
        </section>

        <section className="camera-grid">
          {cameraCards.map((camera) => (
            <article key={camera.camera_id} className="camera-card">
              <div className="camera-card-head">
                <div>
                  <p className="camera-kicker">{camera.label}</p>
                  <h3>{camera.filename}</h3>
                </div>
                <div className="camera-status">{camera.status}</div>
              </div>

              <p className="upload-meta">
                {camera.run
                  ? `Wrong-way ${camera.run.wrong_way_count} | Stops ${camera.run.stop_count} | Duration ${Math.round(
                      camera.run.duration_ms / 1000,
                    )}s`
                  : 'Waiting for analysis run to start.'}
              </p>

              <div className="video-frame-wrap">
                {camera.run && !camera.hasStreamFallback ? (
                  <img
                    key={`${camera.camera_id}-${camera.run.id}-${showGuideLines}`}
                    src={camera.streamUrl}
                    className="video-frame"
                    alt={`${camera.label} detection stream`}
                    onError={() => handleStreamError(camera.camera_id)}
                  />
                ) : camera.sourceUrl ? (
                  <video
                    key={camera.sourceUrl}
                    controls
                    autoPlay
                    muted
                    playsInline
                    loop
                    src={camera.sourceUrl}
                    preload="metadata"
                    className="video-frame"
                  />
                ) : (
                  <p className="upload-meta">Camera source is unavailable.</p>
                )}
              </div>

              <div className="camera-incidents">
                {camera.events.length === 0 ? (
                  <span className="incident-pill incident-pill-muted">No incidents reported yet</span>
                ) : (
                  camera.events.slice(0, 3).map((event) => (
                    <span key={`${camera.camera_id}-${event.id}`} className={`incident-pill incident-${event.event_type}`}>
                      {formatIncidentType(event.event_type)}
                      {event.track_id != null ? ` • Track ${event.track_id}` : ''}
                    </span>
                  ))
                )}
              </div>

              <div className="camera-footnote">
                <span>{formatFps(camera.run?.analyzed_video_fps)}</span>
                <span>{camera.sourceUrl ? 'Source ready' : 'Source missing'}</span>
              </div>
            </article>
          ))}
        </section>

        <StatsCards cameras={cameraCards} />
        <IncidentTable events={flattenedEvents} />
      </main>
    </DashboardLayout>
  )
}
