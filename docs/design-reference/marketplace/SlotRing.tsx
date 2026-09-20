interface SlotRingProps {
  total: number;
  filled: number;
  size?: number;
}

/**
 * Draws the circle's member slots as literal dots arranged in a ring —
 * filled dots are taken slots, hollow dots are open ones. Ties the visual
 * language back to the product's core metaphor (a savings "circle").
 */
export default function SlotRing({ total, filled, size = 64 }: SlotRingProps) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.41;
  const dotR = size * 0.069;

  const dots = Array.from({ length: total }, (_, i) => {
    const angle = (i / total) * 2 * Math.PI - Math.PI / 2;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    const isFilled = i < filled;
    return (
      <circle
        key={i}
        cx={x}
        cy={y}
        r={dotR}
        fill={isFilled ? "var(--ajo-terracotta)" : "var(--ajo-card)"}
        stroke={isFilled ? "var(--ajo-terracotta)" : "var(--ajo-line)"}
        strokeWidth={1.4}
      />
    );
  });

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`${filled} of ${total} slots filled`}
    >
      {dots}
    </svg>
  );
}
