import { useEffect, useRef, useState } from 'react'
import DashboardLayout from '../components/DashboardLayout'
import IncidentTable from '../components/IncidentTable'
import StatsCards from '../components/StatsCards'
import { fetchDashboardSummary, uploadVideo } from '../services/api'

const BACKEND_ORIGIN = 'http://127.0.0.1:8000'

function toAbsoluteUploadUrl(url) {
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

export default function DashboardPage() {
  const [latestRun, setLatestRun] = useState(null)
  const [recentEvents, setRecentEvents] = useState([])
  const [selectedFile, setSelectedFile] = useState(null)
  const [statusMessage, setStatusMessage] = useState('Upload a video to start analysis.')
  const [videoSrc, setVideoSrc] = useState(null)
  const [useDirectVideoUrl, setUseDirectVideoUrl] = useState(false)
  const [useStreamFallback, setUseStreamFallback] = useState(true)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [pendingVideoFocus, setPendingVideoFocus] = useState(false)
  const videoSectionRef = useRef(null)

  async function refreshSummary() {
    const summary = await fetchDashboardSummary()
    setLatestRun(summary.latest_run)
    setRecentEvents(summary.recent_events ?? [])

    const analyzedUrl = summary.latest_run?.analyzed_video_url ?? null
    if (analyzedUrl) {
      setVideoSrc(useDirectVideoUrl ? toAbsoluteUploadUrl(analyzedUrl) : analyzedUrl)
      if (isAnalyzing) {
        setStatusMessage('Analyzed output ready. Playing now...')
        setIsAnalyzing(false)
      }
    } else {
      setVideoSrc(null)
    }
  }

  useEffect(() => {
    refreshSummary().catch(() => setStatusMessage('Backend not reachable yet. Starting backend should fix this.'))

    const timer = setInterval(() => {
      refreshSummary().catch(() => {
        // Keep last successful data rendered; only update status.
        setStatusMessage('Waiting for backend on 127.0.0.1:8000...')
      })
    }, isAnalyzing ? 1000 : 5000)

    return () => clearInterval(timer)
  }, [useDirectVideoUrl, isAnalyzing])

  useEffect(() => {
    if (!pendingVideoFocus || !latestRun || !videoSectionRef.current) {
      return
    }

    videoSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setPendingVideoFocus(false)
  }, [latestRun, pendingVideoFocus])

  function handleVideoError() {
    if (!latestRun?.analyzed_video_url) {
      return
    }

    if (!useDirectVideoUrl) {
      // Retry with direct backend URL when relative proxy path cannot resolve.
      setUseDirectVideoUrl(true)
      setVideoSrc(toAbsoluteUploadUrl(latestRun.analyzed_video_url))
      setStatusMessage('Retrying video using direct backend URL...')
      return
    }

    if (!useStreamFallback) {
      // Final fallback: browser-safe MJPEG stream from backend.
      setUseStreamFallback(true)
      setStatusMessage('Switching to stream fallback for reliable playback...')
    }
  }

  function handleStreamError() {
    if (!useStreamFallback) {
      return
    }

    setUseStreamFallback(false)
    setUseDirectVideoUrl(false)
    setStatusMessage('Stream unavailable. Trying analyzed video file...')
  }

  async function handleUpload(event) {
    event.preventDefault()

    if (!selectedFile) {
      setStatusMessage('Choose a video file first.')
      return
    }

    setStatusMessage('Uploading video and starting analysis...')
    setUseDirectVideoUrl(false)
    setUseStreamFallback(true)
    setIsAnalyzing(true)
    setPendingVideoFocus(true)
    try {
      const run = await uploadVideo(selectedFile)
      setLatestRun(run)
      setStatusMessage('Analysis started. Streaming output as frames become available...')

      // Refresh summary in the background to update counts/events as processing finishes.
      refreshSummary().catch(() => null)
    } catch {
      setIsAnalyzing(false)
      setStatusMessage('Upload failed. Check the backend service and try again.')
    }
  }

  return (
    <DashboardLayout>
      <main className="dashboard-page">
        <header className="hero-panel">
          <div>
            <p className="eyebrow">Tunnel safety operations</p>
            <h1>Emergency dashboard for live tunnel incident monitoring</h1>
            <p className="lede">
              FastAPI back end, PostgreSQL persistence, OpenCV video processing, and ML events surfaced in one operator view.
            </p>
          </div>
          <div className="hero-status">
            <span className="pulse" />
            {statusMessage}
          </div>
        </header>

        <section className="upload-panel">
          <form onSubmit={handleUpload} className="upload-form">
            <label>
              Upload tunnel video
              <input type="file" accept="video/*" onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} />
            </label>
            <button type="submit">Analyze video</button>
          </form>
          {latestRun ? (
            <p className="upload-meta">Last run: {latestRun.original_filename} | duration {latestRun.duration_ms} ms</p>
          ) : (
            <p className="upload-meta">No processed videos yet.</p>
          )}
        </section>

        {latestRun ? (
          <section className="video-grid" ref={videoSectionRef}>
            <article className="video-card">
              <div className="video-card-head">
                <h3>Analyzed Detection Video</h3>
                <span>{formatFps(latestRun.analyzed_video_fps)}</span>
              </div>
              <p className="upload-meta">Green: correct direction | Red: wrong-way | Orange: stop</p>
              {useStreamFallback && latestRun ? (
                <img
                  src={`${BACKEND_ORIGIN}/api/v1/videos/analyzed/stream?run_id=${latestRun.id}&_=${Date.now()}`}
                  className="video-frame"
                  alt="Analyzed detection stream"
                  onError={handleStreamError}
                />
              ) : videoSrc ? (
                <video
                  key={videoSrc}
                  controls
                  autoPlay
                  muted
                  playsInline
                  src={videoSrc}
                  preload="metadata"
                  className="video-frame"
                  onError={handleVideoError}
                />
              ) : (
                <p className="upload-meta">Analyzed output is not generated yet.</p>
              )}
            </article>
          </section>
        ) : null}

        <StatsCards run={latestRun} />
        <IncidentTable events={recentEvents} />
      </main>
    </DashboardLayout>
  )
}
