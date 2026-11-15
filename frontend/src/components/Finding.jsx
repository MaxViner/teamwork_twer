import { useEffect, useState } from "react";
import Button from "./ui/Button.jsx";
import { SOURCE_LABELS, REVIEW_LABELS } from "../constants/labels.js";
import { fileUrl } from "../utils/fileUrl.js";
import { formatTime } from "../utils/formatTime.js";

export default function Finding({ item, jobId, busy, onSeek, onSave, onError }) {
  const [text, setText] = useState(item.corrected_text ?? item.text);
  const [review, setReview] = useState(item.review);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setText(item.corrected_text ?? item.text);
    setReview(item.review);
  }, [item.id, item.corrected_text, item.review]);

  const isImage = /\.(jpg|jpeg|png)$/i.test(item.artifact || "");

  const save = async () => {
    setSaving(true);
    try { await onSave(item.id, { text, review }); } catch (error) { onError(error.message); } finally { setSaving(false); }
  };

  return (
    <article className={`finding review-${item.review}`}>
      <header className="finding-header">
        <span className="badge">{SOURCE_LABELS[item.source]}</span>
        <button className="time-button" onClick={() => onSeek(item.start)}>{formatTime(item.start)}{item.end > item.start ? ` — ${formatTime(item.end)}` : ""}</button>
      </header>

      {isImage && <a href={fileUrl(jobId, item.artifact)} target="_blank" rel="noreferrer"><img className="crop" src={fileUrl(jobId, item.artifact)} alt={`Фрагмент: ${item.text}`} loading="lazy" /></a>}
      <p className="original"><strong>Оригинал:</strong> {item.text}</p>
      {item.recognition_score != null && <p className="muted">Оценка OCR: {(item.recognition_score * 100).toFixed(1)}% · не вероятность геолокации</p>}

      <label>Исправленный текст<textarea value={text} onChange={(event) => setText(event.target.value)} disabled={busy || saving} rows={3} /></label>

      <div className="finding-actions">
        <select value={review} onChange={(event) => setReview(event.target.value)} disabled={busy || saving} aria-label="Результат проверки">
          {Object.entries(REVIEW_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <Button onClick={save} disabled={busy || saving}>{saving ? "Сохраняю…" : "Сохранить"}</Button>
      </div>

      <div className="artifact-links">
        {item.frame_artifact && <a href={fileUrl(jobId, item.frame_artifact)} target="_blank" rel="noreferrer">Полный кадр</a>}
        {item.artifact && !isImage && <a href={fileUrl(jobId, item.artifact)} target="_blank" rel="noreferrer">Исходный артефакт</a>}
      </div>

      <details><summary>Данные анализатора</summary><pre>{JSON.stringify({ extractor: item.extractor, bbox: item.bbox, ...item.data }, null, 2)}</pre></details>
    </article>
  );
}
