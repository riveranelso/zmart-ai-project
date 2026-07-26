export function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center text-gray-500">
      {message}
    </div>
  );
}
