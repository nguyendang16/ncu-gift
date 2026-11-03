/** The analyst's face: the same cartoon head as the round button, without the signal waves. */
export function RobotMark() {
  return (
    <svg className="bot-mark" viewBox="0 -1.2 32 32" aria-hidden="true">
      <line x1="16" y1="6.2" x2="16" y2="8.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="16" cy="4.8" r="1.65" fill="#fff3c4" stroke="currentColor" strokeWidth="1.5" />
      <rect x="2.3" y="12.4" width="3.1" height="5.4" rx="1.4" fill="currentColor" />
      <rect x="26.6" y="12.4" width="3.1" height="5.4" rx="1.4" fill="currentColor" />
      <rect x="5.2" y="8" width="21.6" height="18.4" rx="6.4" fill="#fff3c4" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="12.1" cy="15.3" r="1.75" fill="currentColor" />
      <circle cx="19.9" cy="15.3" r="1.75" fill="currentColor" />
      <path d="M12.3 19.8c1.05 1.15 2.25 1.7 3.7 1.7s2.65-.55 3.7-1.7" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
