const POSITIVE = ["won", "confirmed", "showed", "qualified"];
const NEGATIVE = ["lost", "cancelled", "noshow", "no-show", "abandoned"];

function toneFor(status?: string) {
  const normalized = status?.toLowerCase() ?? "";
  if (POSITIVE.includes(normalized)) {
    return "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400";
  }
  if (NEGATIVE.includes(normalized)) {
    return "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400";
  }
  return "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300";
}

export function Badge({ status }: { status?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${toneFor(status)}`}
    >
      {status ?? "—"}
    </span>
  );
}
