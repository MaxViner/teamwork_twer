export default function StageIcon({ status }) {
    if (status === "running") {
        return (
            <span
                className="stage-spinner"
                aria-hidden="true"
            />
        );
    }


    if (status === "completed") {
        return (
            <svg
                className="stage-status-icon"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
            >
                <path
                    d="m5 12 4 4L19 6"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />
            </svg>
        );
    }


    if (status === "failed") {
        return (
            <svg
                className="stage-status-icon"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
            >
                <path
                    d="m7 7 10 10M17 7 7 17"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                />
            </svg>
        );
    }


    if (status === "skipped") {
        return (
            <svg
                className="stage-status-icon"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
            >
                <path
                    d="M6 12h12"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                />
            </svg>
        );
    }


    return (
        <svg
            className="stage-status-icon"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
        >
            <circle
                cx="12"
                cy="12"
                r="8"
                stroke="currentColor"
                strokeWidth="1.8"
            />


            <path
                d="M12 7v5l3 2"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
}