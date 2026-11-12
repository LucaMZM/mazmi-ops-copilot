/**
 * MAZMI's robot: a rounded head with a dark visor and two upright eyes, plus an offset
 * antenna. Drawn on a 24-unit grid so it stays recognizable at 24 px (favicon, avatars).
 *
 * Colours come from CSS so one asset works in light and dark: the head uses currentColor,
 * the visor `--robot-visor` and the eyes `--robot-eye`. Decorative by default; pass `title`
 * when the robot is the only content of a control or heading.
 */
export function RobotMark({
  size = 24,
  title,
  className,
}: {
  size?: number;
  title?: string;
  className?: string;
}) {
  return (
    <svg
      className={`robotMark ${className ?? ""}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      <circle cx="15.5" cy="2.6" r="1.5" fill="currentColor" />
      <path d="M14.6 3.6 13 6.2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" fill="none" />
      <rect x="2.5" y="6" width="19" height="15.5" rx="6.2" fill="currentColor" />
      <rect className="robotVisor" x="5.4" y="10" width="13.2" height="7.6" rx="3.8" />
      <g className="robotEyes">
        <rect x="8.3" y="11.7" width="2.3" height="4.2" rx="1.15" />
        <rect x="13.4" y="11.7" width="2.3" height="4.2" rx="1.15" />
      </g>
    </svg>
  );
}
