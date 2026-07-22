export function SectionDivider({ label }: { label?: string }) {
  return (
    <div className="divider-ornate" style={{ margin: '24px 0' }}>
      <span className="diamond" />
      {label && (
        <span style={{ fontSize: '0.85rem', letterSpacing: '0.1em' }}>{label}</span>
      )}
      <span className="diamond" />
    </div>
  )
}
