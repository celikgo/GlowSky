export function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <div className="placeholder">
      <div className="placeholder__title">{title}</div>
      <div>{note}</div>
    </div>
  );
}
