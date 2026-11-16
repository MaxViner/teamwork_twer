import { useState } from "react";
import Button from "./ui/Button.jsx";


const DEFAULT_OPTIONS = {
  speech: true,
  ocr: true,
  metadata: false,
  language: null,
  max_frames: 12,
  whisper_model: "small",
};


export default function UploadPanel({ uploading, onUpload }) {
  const [file, setFile] = useState(null);
  const [options, setOptions] = useState(DEFAULT_OPTIONS);

  const set = (name, value) =>
    setOptions((current) => ({
      ...current,
      [name]: value,
    }));

  return (
    <section className="panel">
      <h2>Новое видео</h2>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          onUpload({ file, options });
        }}
      >
        <input
          type="file"
          accept="video/*"
          required
          onChange={(event) =>
            setFile(event.target.files?.[0] || null)
          }
        />

        <div className="options">
          <label className="check">
            <input
              type="checkbox"
              checked={options.speech}
              onChange={(event) =>
                set("speech", event.target.checked)
              }
            />
            Распознавать речь
          </label>

          <label className="check">
            <input
              type="checkbox"
              checked={options.ocr}
              onChange={(event) =>
                set("ocr", event.target.checked)
              }
            />
            Читать надписи: RU + EN
          </label>

          <label className="check">
            <input
              type="checkbox"
              checked={options.metadata}
              onChange={(event) =>
                set("metadata", event.target.checked)
              }
            />
            Читать GPS и метаданные
          </label>

          <label className="check">
            <input
              type="checkbox"
              checked={options.visual}
              onChange={(event) =>
                set("visual", event.target.checked)
              }
            />
            Визуальные признаки и пространственные отношения
          </label>

          <label className="check">
            <input
              type="checkbox"
              checked={options.audio_events}
              onChange={(event) =>
                set("audio_events", event.target.checked)
              }
            />
            Звуковые события
          </label>

          <label className="check">
            <input
              type="checkbox"
              checked={options.structure}
              onChange={(event) =>
                set("structure", event.target.checked)
              }
            />
            Порядок кадров и похожие объекты
          </label>
        </div>

        <div className="form-grid">
          <label>
            Кадров для поиска надписей
            <input
              type="number"
              min="1"
              max="50"
              value={options.max_frames}
              onChange={(event) =>
                set("max_frames", Number(event.target.value))
              }
            />
          </label>

          <label>
            Язык речи
            <select
              value={options.language || ""}
              onChange={(event) =>
                set("language", event.target.value || null)
              }
            >
              <option value="">Автоматически</option>
              <option value="ru">Русский</option>
              <option value="en">Английский</option>
              <option value="ko">Корейский</option>
            </select>
          </label>

          <label>
            Модель Whisper
            <select
              value={options.whisper_model}
              onChange={(event) =>
                set("whisper_model", event.target.value)
              }
            >
              <option value="tiny">tiny</option>
              <option value="base">base</option>
              <option value="small">small</option>
              <option value="medium">medium</option>
            </select>
          </label>
          <label>
              Кадров для визуального анализа

              <input
                type="number"
                min="1"
                max="40"
                value={options.visual_frames}
                onChange={(event) => {
                  set(
                    "visual_frames",
                    Number(event.target.value)
                  );
                }}
              />
            </label>
        </div>

        <p className="muted">
          До 1 ГиБ и 20 минут. Первый запуск может скачивать модели.
          Для GPS нужен ExifTool.
        </p>

        <Button
          variant="primary"
          type="submit"
          disabled={uploading || !file}
        >
          {uploading ? "Загружаю…" : "Загрузить и проанализировать"}
        </Button>
      </form>
      <p className="muted">
      Визуальный анализ использует локальную модель.
      Первый запуск скачивает веса и может потребовать
      значительного объёма памяти. Для проверки начните
      с 3–6 кадров короткого видео.
    </p>
    </section>
  );
}