export default function IncidentTable({ events = [] }) {
  return (
    <section className="table-card">
      <div className="table-head">
        <h2>Recent events</h2>
        <span>Video analysis output</span>
      </div>
      <div className="table-body">
        {events.length === 0 ? (
          <div className="table-row table-row-empty">
            <span>No detection events yet.</span>
          </div>
        ) : (
          events.map((event) => (
            <div key={event.id} className="table-row">
              <strong>{event.event_type}</strong>
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
