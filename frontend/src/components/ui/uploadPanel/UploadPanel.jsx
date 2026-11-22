import { useId, useRef, useState } from "react";
import UploadOptions from "./UploadOptions.jsx";
import UploadSettings from "./UploadSettings.jsx";
import UploadActions from "./UploadActions.jsx";
import {
    DEFAULT_UPLOAD_OPTIONS,
} from "../../../constants/uploadOptions.js";
import './uploadpanelStyles.css'



export default function UploadPanel({
    uploading,
    uploadProgress,
    preparing,
    prepareProgress,
    prepareMessage,
    onUpload,
}) {
    const panelId = useId();
    const contentId = `${panelId}-content`;

    const fileInputRef = useRef(null);




    const [isExpanded, setIsExpanded] = useState(true);




    const [file, setFile] = useState(null);




    const [options, setOptions] = useState(
        DEFAULT_UPLOAD_OPTIONS,
    );




    const setOption = (name, value) =>
        setOptions((current) => ({
            ...current,
            [name]: value,
        }));




    const toggleExpanded = () =>
        setIsExpanded((current) => !current);




    const status = uploading
        ? `Загрузка ${uploadProgress}%`
        : preparing
            ? `Подготовка ${prepareProgress}%`
            : file
                ? file.name
                : "Видео не выбрано";




    return (
        <section className="panel upload-panel">
            <div className="upload-panel-header">
                <div className="upload-panel-title">
                    <h2>Панель загрузки видео</h2>




                    <p className="muted upload-panel-status">
                        {status}
                    </p>
                </div>




                <button
                    type="button"
                    className="upload-panel-toggle"
                    onClick={toggleExpanded}
                    aria-expanded={isExpanded}
                    aria-controls={contentId}
                >
                    <span className="upload-panel-toggle-label">
                        {isExpanded ? "Свернуть" : "Развернуть"}
                    </span>




                    <span
                        className="upload-panel-toggle-icon"
                        aria-hidden="true"
                    >
                        <svg
                            width="18"
                            height="18"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        >
                            <polyline points="6 9 12 15 18 9" />
                        </svg>
                    </span>
                </button>
            </div>




            <div
                id={contentId}
                className={`upload-panel-content${
                    isExpanded ? " is-expanded" : ""
                }`}
            >
                <div className="upload-panel-content-inner">
                    <form
                        onSubmit={(event) => {
                            event.preventDefault();
                            onUpload({
                                file,
                                options,
                            });
                        }}
                    >
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="video/*"
                            required
                            onChange={(event) =>
                                setFile(
                                    event.target.files?.[0]
                                    || null,
                                )
                            }
                        />







                        <UploadActions
                            uploading={uploading}
                            uploadProgress={uploadProgress}
                            preparing={preparing}
                            prepareProgress={prepareProgress}
                            prepareMessage={prepareMessage}
                            hasFile={Boolean(file)}
                        />







                        <UploadOptions
                            options={options}
                            onChange={setOption}
                        />







                        <UploadSettings
                            options={options}
                            onChange={setOption}
                        />







                        <p className="muted">
                            До 1 ГиБ и 20 минут. GPS и теги
                            читаются из файла без внешних утилит.
                            Первый запуск может скачать модели
                            для речи, текста и сцены.
                        </p>
                    </form>
                </div>
            </div>
        </section>
    );
}