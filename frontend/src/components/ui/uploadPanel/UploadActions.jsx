import Button from "../../ui/Button.jsx";



function clampPercent(value) {
    return Math.max(
        0,
        Math.min(
            100,
            Number(value) || 0,
        ),
    );
}



export default function UploadActions({
    uploading,
    uploadProgress,
    preparing,
    prepareProgress,
    prepareMessage,
    hasFile,
}) {
    const percent = clampPercent(uploadProgress);


    const preparePercent = (
        prepareProgress == null
            ? null
            : clampPercent(prepareProgress)
    );


    const busy = uploading || preparing;


    const label = preparing
        ? "Подготовка видео…"
        : uploading
            ? (
                percent >= 100
                    ? "Запускаю анализ…"
                    : `Загружаю… ${percent}%`
            )
            : "Загрузить и проанализировать";


    return (
        <div className="form-actions">
            <Button
                variant="primary"
                type="submit"
                disabled={busy || !hasFile}
            >
                {label}
            </Button>


            {preparing ? (
                <div className="upload-progress">
                    <div
                        className={
                            "upload-progress-bar"
                            + (
                                preparePercent == null
                                    ? " is-indeterminate"
                                    : ""
                            )
                        }
                        role="progressbar"
                        aria-label="Подготовка видео к анализу"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={
                            preparePercent == null
                                ? undefined
                                : Math.round(preparePercent)
                        }
                        aria-valuetext={
                            prepareMessage
                            || "Подготовка видео"
                        }
                    >
                        <span
                            className="upload-progress-fill"
                            style={
                                preparePercent == null
                                    ? undefined
                                    : {
                                        width: `${preparePercent}%`,
                                    }
                            }
                        />
                    </div>


                    <span className="muted">
                        {preparePercent == null
                            ? (
                                prepareMessage
                                || "Готовлю видео к анализу…"
                            )
                            : `Подготовка видео… ${
                                Math.round(preparePercent)
                            }%`}
                    </span>


                    {preparePercent != null && prepareMessage && (
                        <span className="muted">
                            {prepareMessage}
                        </span>
                    )}
                </div>
            ) : uploading && (
                <div className="upload-progress">
                    <div
                        className="upload-progress-bar"
                        role="progressbar"
                        aria-label="Прогресс загрузки видео"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={percent}
                    >
                        <span
                            className="upload-progress-fill"
                            style={{
                                width: `${percent}%`,
                            }}
                        />
                    </div>


                    <span className="muted">
                        {percent >= 100
                            ? "Файл передан, сервер создаёт задание…"
                            : `Передано ${percent}% файла`}
                    </span>
                </div>
            )}
        </div>
    );
}
