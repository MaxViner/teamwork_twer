const MIN_FRAMES = 1;
const MAX_FRAMES = 1500;

export default function UploadSettings({ options, onChange }) {
    return (
        <div className="form-grid">
            <label>
                Кадров для анализа (1–1500)
                <input
                    type="number"
                    min={MIN_FRAMES}
                    max={MAX_FRAMES}
                    step={1}
                    required
                    value={options.max_frames}
                    onChange={(event) => {
                        const { value, valueAsNumber } = event.currentTarget;
                        onChange(
                            "max_frames",
                            value === "" ? "" : valueAsNumber,
                        );
                    }}
                />
            </label>

            <label>
                Язык речи
                <select
                    value={options.language || ""}
                    onChange={(event) =>
                        onChange("language", event.target.value || null)
                    }
                >
                    <option value="">Автоматически</option>
                    <option value="ru">Русский</option>
                    <option value="en">Английский</option>
                </select>
            </label>

            <label>
                Модель Whisper
                <select
                    value={options.whisper_model}
                    onChange={(event) =>
                        onChange("whisper_model", event.target.value)
                    }
                >
                    <option value="tiny">tiny</option>
                    <option value="base">base</option>
                    <option value="small">small</option>
                    <option value="medium">medium</option>
                </select>
            </label>
        </div>
    );
}
