const FIRST_RADIUS = 60;
const LAST_RADIUS = 1800;
const RADIUS_STEP = 16;
const CENTRE_OFFSET = -140;

const RADII = Array.from(
  { length: Math.floor((LAST_RADIUS - FIRST_RADIUS) / RADIUS_STEP) + 1 },
  (_, index) => FIRST_RADIUS + index * RADIUS_STEP,
);

type RailProps = {
  side: "left" | "right";
  centreY: string;
};

function Rail({ side, centreY }: RailProps) {
  const position =
    side === "left" ? "left-0" : "right-0 -scale-x-100";
  return (
    <div
      className={`absolute inset-y-0 w-[calc((100%-var(--frame))/2)] overflow-hidden text-foreground max-compact:hidden ${position}`}
    >
      <svg className="absolute inset-0 size-full" aria-hidden="true">
        {RADII.map((radius) => (
          <circle
            key={radius}
            cx={CENTRE_OFFSET}
            cy={centreY}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeOpacity={0.09}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
    </div>
  );
}

/** Concentric circles filling the areas outside the safe area. */
export function SideRails() {
  return (
    <>
      <Rail side="left" centreY="38%" />
      <Rail side="right" centreY="72%" />
    </>
  );
}
