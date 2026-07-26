export function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-6 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      {children}
    </div>
  );
}
