export default function IncidentTable({ events = [] }) {
  return (
    <section className="table-card">
      <div className="table-head">
        <h2>Recent events</h2>
        <span>All four camera feeds</span>
      </div>
      <div className="table-body">
        {events.length === 0 ? (
          <div className="table-row table-row-empty">
            <span>No detection events yet.</span>
          </div>
        ) : (
          events.map((event) => (
            <div key={event.id} className="table-row">
              <strong>{event.camera_label ?? 'Camera'}</strong>
              <span>{event.event_type}</span>
              <span>Track {event.track_id ?? '-'}</span>
              <span>{Math.round(event.timestamp_ms / 1000)}s</span>
              <span>{event.details ? JSON.stringify(event.details) : '-'}</span>
            </div>
          ))
        )}
      </div>
    </section>
  )
}
