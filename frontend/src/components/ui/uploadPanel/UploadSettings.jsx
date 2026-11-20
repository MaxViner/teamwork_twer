export default function UploadSettings({
    options,
    onChange,
}) {
    return (
        <div className="form-grid">
            <label>
                Кадров для анализа
                <input
                    type="number"
                    min="1"
                    max="2000"
                    step="50"
                    value={options.max_frames}
                    onChange={(event) =>
                        onChange(
                            "max_frames",
                            Number(
                                event.target.value,
                            ),
                        )
                    }
                />
            </label>


            <label>
                Язык речи
                <select
                    value={options.language || ""}
                    onChange={(event) =>
                        onChange(
                            "language",
                            event.target.value || null,
                        )
                    }
                >
                    <option value="">
                        Автоматически
                    </option>


                    <option value="ru">
                        Русский
                    </option>


                    <option value="en">
                        Английский
                    </option>
                </select>
            </label>


            <label>
                Модель Whisper
                <select
                    value={options.whisper_model}
                    onChange={(event) =>
                        onChange(
                            "whisper_model",
                            event.target.value,
                        )
                    }
                >
                    <option value="tiny">
                        tiny
                    </option>


                    <option value="base">
                        base
                    </option>


                    <option value="small">
                        small
                    </option>


                    <option value="medium">
                        medium
                    </option>
                </select>
            </label>
        </div>
    );
}