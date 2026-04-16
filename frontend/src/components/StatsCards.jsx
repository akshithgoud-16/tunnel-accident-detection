export default function StatsCards({ run }) {
  const stats = [
    { label: 'Wrong-way count', value: run?.wrong_way_count ?? 0 },
    { label: 'Stop count', value: run?.stop_count ?? 0 },
    { label: 'Video duration', value: run ? `${Math.round(run.duration_ms / 1000)}s` : '0s' },
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
