// Logo Osirion — hexagone au trait + cercle rouge + iris (SVG inline).
// Le rouge est ici IDENTITAIRE (logo), pas une alerte.
export function OsMark({ size = 28, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M12 1.6 L21.0 6.8 L21.0 17.2 L12 22.4 L3.0 17.2 L3.0 6.8 Z"
        fill="#0d0f12" stroke="var(--os-red)" strokeOpacity="0.5" strokeWidth="1.2"
      />
      <circle cx="12" cy="12" r="5.1" stroke="var(--os-red)" strokeWidth="2.4" fill="none" />
      <circle cx="12" cy="12" r="2.4" fill="#2c333b" />
      <circle cx="12" cy="12" r="1.05" fill="#ffffff" />
    </svg>
  );
}

export default function OsLogo({ size = 26, wordmark = true, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <OsMark size={size} />
      {wordmark && (
        <span className="font-bold tracking-[0.06em] text-white text-[14px] leading-none whitespace-nowrap">QWIPER SENTINEL</span>
      )}
    </span>
  );
}
