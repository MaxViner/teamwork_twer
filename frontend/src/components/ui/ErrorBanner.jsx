export default function ErrorBanner({ message, onClose }) {
  if (!message) return null;
  return <div className="error" role="alert"><span>{message}</span><button onClick={onClose}>Закрыть</button></div>;
}
