import { useEffect, useState } from "react";
import StageCard from "../ui/stageCard/StageCard";
import './StagePanel.css'
// Порядок совпадает с STAGES в backend/app/APIGateway/pipeline.py
const STAGE_ORDER = [
  "prepare",
  "metadata",
  "scenes",
  "speech",
  "audio_structure",
  "ocr",
  "structure",
  "scene_objects",
  "faces",
  "visual_profile",
  "road_geometry",
  "location_evidence",
  "summary",
  "video_structure",
  "comprehension",
  "landmarks",
  "ai_prompt",
];

const STAGE_LABELS = {
  prepare: "Подготовка видео",
  metadata: "Метаданные",
  scenes: "Поиск сцен",
  speech: "Распознавание речи",
  audio_structure: "Аудиопрофиль",
  ocr: "Текст на кадрах",
  structure: "Повторы",
  scene_objects: "Объекты и типы сцен",
  faces: "Лица",
  visual_profile: "Визуальный профиль",
  road_geometry: "Геометрия дороги",
  location_evidence: "Локационное досье",
  summary: "Конспект",
  video_structure: "Структура видео",
  comprehension: "Проверка понимания",
  landmarks: "Ориентиры",
  ai_prompt: "AI-промпт для поиска места",
};

const STATUS_LABELS = {
  pending: "ожидает",
  running: "выполняется",
  completed: "готово",
  failed: "ошибка",
  skipped: "пропущен",
};

function stagePosition(key) {
  const idx = STAGE_ORDER.indexOf(key);
  return idx >= 0 ? idx : STAGE_ORDER.length;
}

export default function CollapsibleStagesPanel({ job, busy, onRetry }) {
  const stages = Object.entries(job?.stages || {}).sort(
    ([a], [b]) => stagePosition(a) - stagePosition(b),
  );

  const [openKeys, setOpenKeys] = useState(() => new Set());

  // При смене задания разворачиваем «активные» этапы — running и failed.
  // Остальные остаются свёрнутыми, чтобы не было шума.
  useEffect(() => {
    const initial = new Set();
    for (const [key, stage] of stages) {
      if (stage.status === "running" || stage.status === "failed") {
        initial.add(key);
      }
    }
    setOpenKeys(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id]);

  const toggle = (key) => {
    setOpenKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const expandAll = () => setOpenKeys(new Set(stages.map(([k]) => k)));
  const collapseAll = () => setOpenKeys(new Set());

  if (stages.length === 0) {
    return (
      <div className="panel">
        <h3>Этапы обработки</h3>
        <p className="muted">Этапы обработки пока отсутствуют.</p>
      </div>
    );
  }

  return (
    <div className="panel stages-panel">
      <div className="stages-panel__header">
        <h3>Этапы обработки</h3>
        <div className="stages-panel__actions">
          <button type="button" className="btn btn-ghost" onClick={expandAll}>
            Развернуть все
          </button>
          <button type="button" className="btn btn-ghost" onClick={collapseAll}>
            Свернуть все
          </button>
        </div>
      </div>

      <div className="stage-accordion">
        {stages.map(([key, stage]) => {
          const isOpen = openKeys.has(key);
          const status = stage.status || "pending";
          const percent =
            typeof stage.progress === "number"
              ? Math.round(stage.progress)
              : null;

          return (
            <div
              key={key}
              className={`stage-accordion__item stage-accordion__item--${status}`}
            >
              <button
                type="button"
                className="stage-accordion__header"
                onClick={() => toggle(key)}
                aria-expanded={isOpen}
              >
                <span className={`stage-status stage-status--${status}`} aria-hidden="true" />
                <span className="stage-accordion__title">
                  {STAGE_LABELS[key] || key}
                </span>
                <span className="stage-accordion__meta">
                  {STATUS_LABELS[status] || status}
                  {percent != null && ` · ${percent}%`}
                </span>
                <span className="stage-accordion__chevron" aria-hidden="true">
                  {isOpen ? "▾" : "▸"}
                </span>
              </button>

              {isOpen && (
                <div className="stage-accordion__body">
                  <StageCard
                    stageKey={key}
                    stage={stage}
                    busy={busy}
                    onRetry={onRetry}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}