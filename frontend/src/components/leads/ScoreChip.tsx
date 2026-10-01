import { TEMP_CHIP, temperature } from "@/lib/labels";

/** Score bucket as a small chip: Hot, Warm, Cold, or Unscored before Maya has spoken to them. */
export function ScoreChip({ score }: { score: number | null | undefined }) {
  const t = temperature(score);
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${TEMP_CHIP[t]}`}>
      {t}{score !== null && score !== undefined ? ` · ${score}` : ""}
    </span>
  );
}
