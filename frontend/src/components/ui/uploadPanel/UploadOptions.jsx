import OptionToggle from "./optionToggle/OptionToggle.jsx";
import { UPLOAD_TOGGLES } from "../../../constants/uploadOptions.js";



export default function UploadOptions({
    options,
    onChange,
}) {
    return (
        <div className="options">
            {UPLOAD_TOGGLES.map((item) => (
                <OptionToggle
                    key={item.name}
                    checked={options[item.name]}
                    onChange={(event) =>
                        onChange(
                            item.name,
                            event.target.checked,
                        )
                    }
                    title={item.title}
                    description={item.description}
                />
            ))}
        </div>
    );
}