import { cn } from "@/lib/cn";
import { SPARK_HEIGHT, SPARK_WIDTH, sparkGeometry, type SparkDirection } from "@/lib/history/spark";

const POINT_SIZE = 3;

const LINE_CLASS: Readonly<Record<SparkDirection, string>> = {
  up: "stroke-success",
  down: "stroke-destructive",
  flat: "stroke-muted-foreground",
};

/**
 * The score trend of an idea: one point per score version, oldest first. A 1px line tinted green
 * when the score went up and red when it went down, 3px square points, the latest filled. Draws
 * nothing with fewer than two versions. The `<title>` lists the totals ("v1 54 → v2 63").
 */
export function ScoreSpark({ totals, className }: { totals: readonly number[]; className?: string }) {
  const geometry = sparkGeometry(totals);
  if (!geometry) return null;
  const last = geometry.points.length - 1;

  return (
    <svg
      width={SPARK_WIDTH}
      height={SPARK_HEIGHT}
      viewBox={`0 0 ${SPARK_WIDTH} ${SPARK_HEIGHT}`}
      role="img"
      aria-label={`Score history ${geometry.title}`}
      className={cn("block shrink-0 overflow-visible", className)}
    >
      <title>{geometry.title}</title>
      <polyline
        points={geometry.points.map((point) => `${point.x},${point.y}`).join(" ")}
        fill="none"
        strokeWidth={1}
        className={LINE_CLASS[geometry.direction]}
      />
      {geometry.points.map((point, index) => (
        <rect
          key={index}
          x={point.x - POINT_SIZE / 2}
          y={point.y - POINT_SIZE / 2}
          width={POINT_SIZE}
          height={POINT_SIZE}
          strokeWidth={1}
          className={index === last ? "fill-foreground stroke-foreground" : "fill-background stroke-muted-foreground"}
        />
      ))}
    </svg>
  );
}
