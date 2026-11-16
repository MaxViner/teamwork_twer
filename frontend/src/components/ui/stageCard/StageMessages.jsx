export default function StageMessages({
  progressMessage,
  note,
  error,
  failed,
  showPreviousResult,
  skipped,
}) {
  if (skipped) {
    return null;
  }

  return (
    <>
      {progressMessage && (
        <p className="stage-operation">
          {progressMessage}
        </p>
      )}

      {note && (
        <p className="stage-note">
          {note}
        </p>
      )}

      {error && (
        <p className="stage-error">
          {error}
        </p>
      )}

      {failed && (
        <p className="stage-note">
          Этап остановлен. На шкале показан последний сохранённый прогресс.
        </p>
      )}

      {showPreviousResult && (
        <p className="stage-note">
          Показан сохранённый результат прошлой попытки.
        </p>
      )}
    </>
  );
}