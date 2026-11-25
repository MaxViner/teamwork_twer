import { useMemo, useState } from "react";
import { formatTime } from "../../../utils/formatTime.js";

const SOUND_ICONS = {
    Train: "🚆",
    "Railway train": "🚆",
    "Subway, metro": "🚇",
    "Subway, metro, underground": "🚇",
    Car: "🚗",
    Truck: "🚚",
    Motorcycle: "🏍️",
    Bus: "🚌",
    Aircraft: "✈️",
    Helicopter: "🚁",
    Ship: "🚢",
    "Boat, Water vehicle": "⛵",
    "Sailboat, sailing ship": "⛵",
    "Motorboat, speedboat": "🚤",
    Siren: "🚨",
    "Police car (siren)": "🚔",
    "Ambulance (siren)": "🚑",
    "Fire engine, fire truck (siren)": "🚒",
    "Emergency vehicle": "🚨",
    "Civil defense siren": "🚨",
    "Church bell": "🔔",
    Bell: "🔔",
    "Bicycle bell": "🔔",
    "Jingle bell": "🔔",
    "Change ringing (campanology)": "🔔",
    "Wind chime": "🎐",
    Chime: "🔔",
    Rain: "🌧️",
    Thunder: "⛈️",
    Thunderstorm: "⛈️",
    Wind: "🌬️",
    Water: "🌊",
    Stream: "🌊",
    Ocean: "🌊",
    "Waves, surf": "🌊",
    Waterfall: "🌊",
    Bird: "🐦",
    "Bird vocalization, bird call, bird song": "🐦",
    Crow: "🐦‍⬛",
    "Pigeon, dove": "🕊️",
    Owl: "🦉",
    Dog: "🐕",
    Cat: "🐈",
    Rooster: "🐓",
    "Chicken, rooster": "🐓",
    Frog: "🐸",
    Cricket: "🦗",
    Cow: "🐄",
    "Cattle, bovinae": "🐄",
    Horse: "🐴",
    Sheep: "🐑",
    Goat: "🐐",
    Whale: "🐋",
    "Whale vocalization": "🐋",
    "Traffic noise, roadway noise": "🚦",
    "Vehicle horn, car horn, honking": "📯",
    "Train whistle": "🚂",
    "Train horn": "🚂",
    "Steam whistle": "🚂",
    Construction: "🏗️",
    Jackhammer: "🔨",
    Drill: "🔧",
    "Power tool": "🔧",
    Chainsaw: "🪚",
    "Lawn mower": "🌱",
    Crowd: "👥",
    Chatter: "🗣️",
    "Hubbub, speech noise, speech babble": "🗣️",
    Music: "🎵",
    Singing: "🎤",
    Choir: "🎤",
    Chant: "🕉️",
    Mantra: "🕉️",
    Alarm: "🚨",
    "Fire alarm": "🚨",
    Foghorn: "📯",
    Explosion: "💥",
    "Gunshot, gunfire": "💥",
    Fireworks: "🎆",
    Firecracker: "🧨",
    Silence: "🤫",
    "Outside, urban or manmade": "🏙️",
    "Outside, rural or natural": "🌾",
    "Inside, public space": "🏛️",
    "Inside, large room or hall": "🏛️",
    "Inside, small room": "🚪",
};

const IMPORTANCE_BADGE = {
    высокая: { label: "важно", className: "is-high" },
    средняя: null,
    низкая: null,
};

function SoundCard({ item, onSeek }) {
    const [expanded, setExpanded] = useState(false);
    const icon = SOUND_ICONS[item.kind] || "🔊";
    const intervals = item.intervals || [];
    const importance = IMPORTANCE_BADGE[item.importance];

    return (
        <div className="sound-card">
            <button
                type="button"
                className="sound-card__header"
                onClick={() => setExpanded((v) => !v)}
                aria-expanded={expanded}
            >
                <span className="sound-card__icon" aria-hidden="true">{icon}</span>
                <div className="sound-card__title">
                    <div className="sound-card__label-row">
                        <strong>{item.label_ru || item.kind}</strong>
                        {importance && (
                            <span className={`sound-card__badge sound-card__badge--${importance.className}`}>
                                {importance.label}
                            </span>
                        )}
                    </div>
                    <span className="sound-card__meta">
                        {item.count} участк. · {item.total_seconds} с
                        {item.max_confidence != null && (
                            <span className="sound-card__conf">
                                {" "}· до {Math.round(item.max_confidence * 100)}%
                            </span>
                        )}
                    </span>
                </div>
                <span className="sound-card__toggle" aria-hidden="true">
                    {expanded ? "▾" : "▸"}
                </span>
            </button>
            {expanded && intervals.length > 0 && (
                <div className="sound-card__intervals">
                    {intervals.map(([start, end], i) => (
                        <button
                            key={`${start}-${i}`}
                            type="button"
                            className="sound-card__time"
                            onClick={() => onSeek?.(start)}
                            title={`${formatTime(start)} — ${formatTime(end)}`}
                        >
                            {formatTime(start)}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

export default function SoundPanel({ job, onSeek, embedded = false }) {
    const stage = job?.stages?.audio_structure;

    const result = stage?.result || {};
    const sounds = result.sound_summary || [];
    const profile = result.profile || {};
    const stageStatus = stage?.status;

    const totalSounds = useMemo(
        () => sounds.reduce((sum, item) => sum + (item.count || 0), 0),
        [sounds],
    );

    if (!stage) return null;

    const className = embedded ? "audio-embedded" : "panel audio-panel";
    const Wrapper = embedded ? "div" : "section";

    if (stageStatus === "skipped") {
        return (
            <Wrapper className={className}>
                {!embedded && (
                    <div className="section-row">
                        <h2>Звуковые события</h2>
                    </div>
                )}
                <p className="muted">
                    {stage.error || "Аудиодорожки нет — звуковой анализ пропущен."}
                </p>
            </Wrapper>
        );
    }

    if (stageStatus === "running") {
        const percent = typeof stage.progress === "number"
            ? Math.round(stage.progress)
            : null;
        return (
            <Wrapper className={className}>
                {!embedded && (
                    <div className="section-row">
                        <h2>Звуковые события</h2>
                    </div>
                )}
                <p className="muted">
                    {stage.progress_message || "Обработка звука…"}
                    {percent != null && ` · ${percent}%`}
                </p>
            </Wrapper>
        );
    }

    if (stageStatus === "failed") {
        return (
            <Wrapper className={className}>
                {!embedded && (
                    <div className="section-row">
                        <h2>Звуковые события</h2>
                    </div>
                )}
                <p className="stage-error">
                    {stage.error || "Ошибка анализа звука."}
                </p>
            </Wrapper>
        );
    }

    const hasSounds = sounds.length > 0;
    const hasProfile = Boolean(profile && Object.keys(profile).length);
    const note = result.note;

    return (
        <Wrapper className={className}>
            {!embedded && (
                <div className="section-row">
                    <h2>Звуковые события</h2>
                    {totalSounds > 0 && (
                        <span className="insight-count">
                            {totalSounds} событий
                        </span>
                    )}
                </div>
            )}

            {embedded && totalSounds > 0 && (
                <p className="audio-embedded__count">
                    {totalSounds} звуковых участков
                </p>
            )}

            <p className="muted audio-panel__intro">
                Звуки распознаны по классам AudioSet. Это улики
                акустической обстановки — не подтверждённые координаты.
            </p>

            {!hasSounds && (
                <p className="muted">
                    {note || "Узнаваемых звуков (транспорт, сирены, колокола, природа, стройка) не найдено."}
                </p>
            )}

            {hasSounds && (
                <>
                    <h4 className="audio-panel__section-title">
                        Идентифицированные звуки
                    </h4>
                    <div className="sound-list">
                        {sounds.map((item) => (
                            <SoundCard
                                key={`${item.kind}-${item.label_ru}`}
                                item={item}
                                onSeek={onSeek}
                            />
                        ))}
                    </div>
                </>
            )}

            {hasProfile && (
                <>
                    <h4 className="audio-panel__section-title">
                        Профиль громкости
                    </h4>
                    <div className="audio-profile">
                        <div className="audio-profile__row">
                            <span>Окружение</span>
                            <strong>{profile.environment || "—"}</strong>
                        </div>
                        <div className="audio-profile__row">
                            <span>Тишина</span>
                            <strong>
                                {Math.round((profile.silence_ratio || 0) * 100)}%
                            </strong>
                        </div>
                        <div className="audio-profile__row">
                            <span>Громкие участки</span>
                            <strong>
                                {Math.round((profile.loud_ratio || 0) * 100)}%
                            </strong>
                        </div>
                        <div className="audio-profile__row">
                            <span>Средний RMS</span>
                            <strong>{profile.mean_rms ?? "—"}</strong>
                        </div>
                        <div className="audio-profile__row">
                            <span>Спектральный центроид</span>
                            <strong>
                                {profile.mean_centroid_hz != null
                                    ? `${profile.mean_centroid_hz} Гц`
                                    : "—"}
                            </strong>
                        </div>
                    </div>
                </>
            )}
        </Wrapper>
    );
}
