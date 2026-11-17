import './optionToggle.css'

export default function OptionToggle({
    checked,
    onChange,
    title,
    description,
}) {
    return (
        <label className="option-toggle">
            <input
                type="checkbox"
                checked={checked}
                onChange={onChange}
            />


            <span className="option-toggle-control">
                <span className="option-toggle-marker" />
            </span>


            <span className="option-toggle-content">
                <span className="option-toggle-title">
                    {title}
                </span>


                {description ? (
                    <span className="option-toggle-description">
                        {description}
                    </span>
                ) : null}
            </span>
        </label>
    );
}