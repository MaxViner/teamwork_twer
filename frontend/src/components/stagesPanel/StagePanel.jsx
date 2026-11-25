import { useEffect, useState } from "react";
import StageCard from "../ui/stageCard/StageCard";
import "./StagePanel.css";

/**
 * Этапы сгруппированы так, как они воспринимаются пользователем:
 * визуальные признаки — один шаг, аудиальные — один шаг.
 *
 * Внутри группы остаются отдельные StageCard: по ним видно прогресс
 * каждой подстадии и можно повторить только упавшую часть.
 */
const STAGE_GROUPS = [
  {
    key: "prepare",
    label: "Подготовка видео",
    stages: ["prepare"],
  },
  {
    key: "metadata",
    label: "Метаданные",
    stages: ["metadata"],
  },
  {
    key: "visual",
    label: "Визуальный анализ",
    stages: ["scenes", "ocr", "visual_analysis"],
  },
  {
    key: "audio",
    label: "Аудиальный анализ",
    stages: ["speech", "audio_structure"],
  },
  {
    key: "place_profile",
    label: "Профиль места",
    stages: ["place_profile"],
  },
  {
    key: "location_evidence",
    label: "Локационное досье",
    stages: ["location_evidence"],
  },
  {
    key: "summary",
    label: "Конспект",
    stages: ["summary"],
  },
  {
    key: "video_structure",
    label: "Структура видео",
    stages: ["video_structure"],
  },
  {
    key: "location_prompt",
    label: "AI-промпт для поиска места",
    stages: ["location_prompt"],
  },
];

// Служебные этапы, которые не показываем в интерфейсе.
const HIDDEN_STAGES = new Set(["structure"]);

const SINGLE_STAGE_LABELS = {
  prepare: "Подготовка видео",
  metadata: "Метаданные",
  place_profile: "Профиль места",
  location_evidence: "Локационное досье",
  summary: "Конспект",
  video_structure: "Структура видео",
  location_prompt: "AI-промпт для поиска места",
};

const STATUS_LABELS = {
  pending: "ожидает",
  running: "выполняется",
  completed: "готово",
  failed: "ошибка",
  skipped: "пропущен",
};

function buildGroups(stages) {
  const used = new Set();
  const groups = [];

  for (const config of STAGE_GROUPS) {
    const items = config.stages
      .filter((key) => stages[key] && !HIDDEN_STAGES.has(key))
      .map((key) => [key, stages[key]]);

    if (!items.length) {
      continue;
    }

    items.forEach(([key]) => used.add(key));

    groups.push({
      ...config,
      label: items.length === 1
        ? SINGLE_STAGE_LABELS[items[0][0]] || config.label
        : config.label,
      items,
    });
  }

  // Незнакомые этапы (например, из старых job.json) не теряем.
  const rest = Object.entries(stages).filter(
    ([key]) => !used.has(key) && !HIDDEN_STAGES.has(key),
  );

  if (rest.length) {
    groups.push({
      key: "other",
      label: "Другие этапы",
      items: rest,
    });
  }

  return groups;
}

function groupStatus(items) {
  const statuses = items.map(([, stage]) => stage.status || "pending");

  if (statuses.includes("running")) return "running";
  if (statuses.includes("failed")) return "failed";
  if (statuses.every((status) => status === "skipped")) return "skipped";
  if (statuses.every((status) => status === "completed" || status === "skipped")) {
    return "completed";
  }
  if (statuses.every((status) => status === "pending" || status === "queued")) {
    return "pending";
  }

  return "pending";
}

function groupPercent(items) {
  const status = groupStatus(items);

  if (status === "completed") return 100;
  if (status === "pending" || status === "skipped") return 0;

  const values = items
    .filter(([, stage]) => stage.status === "running" || stage.status === "failed")
    .map(([, stage]) => (
      typeof stage.progress === "number" ? stage.progress : null
    ))
    .filter((value) => value != null);

  if (!values.length) {
    return null;
  }

  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export default function CollapsibleStagesPanel({ job, busy, onRetry }) {
  const groups = buildGroups(job?.stages || {});

  const [openKeys, setOpenKeys] = useState(() => new Set());

  // При смене задания разворачиваем только активные группы — running
  // и failed, чтобы список не превращался в простыню.
  useEffect(() => {
    const initial = new Set();

    for (const group of buildGroups(job?.stages || {})) {
      const status = groupStatus(group.items);

      if (status === "running" || status === "failed") {
        initial.add(group.key);
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

  const expandAll = () => setOpenKeys(new Set(groups.map((group) => group.key)));
  const collapseAll = () => setOpenKeys(new Set());

  if (groups.length === 0) {
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
        {groups.map((group) => {
          const isOpen = openKeys.has(group.key);
          const status = groupStatus(group.items);
          const percent = groupPercent(group.items);
          const multi = group.items.length > 1;

          return (
            <div
              key={group.key}
              className={`stage-accordion__item stage-accordion__item--${status}`}
            >
              <button
                type="button"
                className="stage-accordion__header"
                onClick={() => toggle(group.key)}
                aria-expanded={isOpen}
              >
                <span className={`stage-status stage-status--${status}`} aria-hidden="true" />

                <span className="stage-accordion__title">
                  {group.label}

                  {multi && (
                    <span className="stage-accordion__subtitle">
                      {group.items.length} подэтапа
                    </span>
                  )}
                </span>

                <span className="stage-accordion__meta">
                  {STATUS_LABELS[status] || status}
                  {percent != null && ` · ${Math.round(percent)}%`}
                </span>

                <span className="stage-accordion__chevron" aria-hidden="true">
                  {isOpen ? "▾" : "▸"}
                </span>
              </button>

              {isOpen && (
                <div className="stage-accordion__body">
                  {group.items.map(([key, stage]) => (
                    <StageCard
                      key={key}
                      stageKey={key}
                      stage={stage}
                      job={job}
                      busy={busy}
                      onRetry={onRetry}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
