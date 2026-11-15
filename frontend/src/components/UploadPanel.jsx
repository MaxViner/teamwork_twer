import { useState } from "react";
import Button from "./ui/Button.jsx";

const DEFAULT_OPTIONS = { speech: true, ocr: true, metadata: false, language: null, max_frames: 12, whisper_model: "small" };

export default function UploadPanel({ uploading, onUpload }) {
  const [file, setFile] = useState(null);
  const [options, setOptions] = useState(DEFAULT_OPTIONS);
  const set = (name, value) => setOptions((current) => ({ ...current, [name]: value }));

  return (
    <section className="panel">
      <h2>Новое видео</h2>
      <form onSubmit={(event) => { event.preventDefault(); onUpload({ file, options }); }}>
        <input type="file" accept="video/*" required onChange={(event) => setFile(event.target.files?.[0] || null)} />

        <div className="options">
          <label className="check"><input type="checkbox" checked={options.speech} onChange={(e) => set("speech", e.target.checked)} />Распознавать речь</label>
          <label className="check"><input type="checkbox" checked={options.ocr} onChange={(e) => set("ocr", e.target.checked)} />Читать надписи: RU + EN</label>
          <label className="check"><input type="checkbox" checked={options.metadata} onChange={(e) => set("metadata", e.target.checked)} />Читать GPS и метаданные</label>
        </div>

        <div className="form-grid">
          <label>Кадров для OCR<input type="number" min="1" max="50" value={options.max_frames} onChange={(e) => set("max_frames", Number(e.target.value))} /></label>
          <label>Язык речи
            <select value={options.language || ""} onChange={(e) => set("language", e.target.value || null)}>
              <option value="">Автоматически</option><option value="ru">Русский</option><option value="en">Английский</option><option value="ko">Корейский</option>
            </select>
          </label>
          <label>Модель Whisper
            <select value={options.whisper_model} onChange={(e) => set("whisper_model", e.target.value)}>
              <option value="tiny">tiny</option><option value="base">base</option><option value="small">small</option><option value="medium">medium</option>
            </select>
          </label>
        </div>

        <p className="muted">До 1 ГиБ и 20 минут. Первый запуск может скачивать модели. Для GPS нужен ExifTool.</p>
        <Button variant="primary" type="submit" disabled={uploading || !file}>{uploading ? "Загружаю…" : "Загрузить и проанализировать"}</Button>
      </form>
    </section>
  );
}
