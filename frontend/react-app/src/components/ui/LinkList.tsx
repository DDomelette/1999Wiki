interface LinkItem {
  label: string
  url: string
  icon?: string
}

const DEFAULT_LINKS: LinkItem[] = [
  { label: '重返未来1999 官网', url: 'https://1999buey.com/', icon: '✦' },
]

export function LinkList({ links = DEFAULT_LINKS }: { links?: LinkItem[] }) {
  return (
    <ul style={{ listStyle: 'none', padding: 0 }}>
      {links.map((l) => (
        <li key={l.url}>
          <a
            href={l.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 12px',
              color: 'var(--text-primary)',
              borderRadius: 4,
              transition: 'background 0.2s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-elevated)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            {l.icon && <span style={{ color: 'var(--accent-gold)' }}>{l.icon}</span>}
            <span>{l.label}</span>
          </a>
        </li>
      ))}
    </ul>
  )
}
