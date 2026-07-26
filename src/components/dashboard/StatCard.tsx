import type { LucideIcon } from "lucide-react";

export function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-6 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-500">
          <Icon size={20} />
        </div>
        <div>
          <div className="text-2xl font-semibold">{value}</div>
          <div className="text-sm text-neutral-500 dark:text-neutral-400">{label}</div>
        </div>
      </div>
    </div>
  );
}
