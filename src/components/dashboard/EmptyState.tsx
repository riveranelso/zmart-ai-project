import { PlugZap } from "lucide-react";

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-neutral-300 p-16 text-center dark:border-neutral-700">
      <PlugZap className="text-neutral-400 dark:text-neutral-600" size={28} />
      <p className="max-w-sm text-sm text-neutral-500 dark:text-neutral-400">
        {message}
      </p>
    </div>
  );
}
