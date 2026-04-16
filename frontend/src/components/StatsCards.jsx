export default function StatsCards({ cameras = [] }) {
  const activeRuns = cameras.filter((camera) => camera.run)
  const stats = [
    { label: 'Cameras online', value: cameras.length },
    { label: 'Running analyses', value: activeRuns.length },
    {
      label: 'Wrong-way count',
      value: cameras.reduce((total, camera) => total + (camera.run?.wrong_way_count ?? 0), 0),
    },
    {
      label: 'Stop count',
      value: cameras.reduce((total, camera) => total + (camera.run?.stop_count ?? 0), 0),
    },
  ]

  return (
    <section className="stats-grid">
      {stats.map((item) => (
        <article key={item.label} className="stat-card">
          <p>{item.label}</p>
          <strong>{item.value}</strong>
        </article>
      ))}
    </section>
  )
}
