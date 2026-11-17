import { useRef, useState } from "react";
import UploadOptions from "./UploadOptions.jsx";
import UploadSettings from "./UploadSettings.jsx";
import UploadActions from "./UploadActions.jsx";
import {
    DEFAULT_UPLOAD_OPTIONS,
} from "../../../constants/uploadOptions.js";




export default function UploadPanel({
    uploading,
    onUpload,
}) {
    const fileInputRef = useRef(null);


    const [file, setFile] = useState(null);


    const [options, setOptions] = useState(
        DEFAULT_UPLOAD_OPTIONS,
    );



    const setOption = (name, value) =>
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



                <UploadActions
                    uploading={uploading}
                    hasFile={Boolean(file)}
                />
            </form>
        </section>
    );
}