import { Link, Outlet, useLocation } from "react-router-dom";
import PageHeader from "../../layout/PageHeader.jsx";
import "../../styles/dev.css";


const TOOLS = [
    { to: "/dev/vision", label: "Визуальный анализ" },
    { to: "/dev/video-lab", label: "Видео-лаб" },
    { to: "/dev/odometry", label: "Одометрия и BEV" },
    { to: "/dev/map", label: "Карт-исследование" },
    { to: "/dev/chat", label: "AI API чат" },
];


export default function DevLayout() {
    const location = useLocation();

    return (
        <main className="app">
            <PageHeader />


            <nav className="panel">
                <h2>Тестовые инструменты</h2>

                <p className="muted">
                    Точечная проверка сервисов без полного pipeline.
                </p>


                <div className="insight-chips">
                    {TOOLS.map((tool) => (
                        <Link
                            key={tool.to}
                            to={tool.to}
                            className={
                                "insight-chip insight-chip-button"
                                + (
                                    location.pathname === tool.to
                                        ? " is-active"
                                        : ""
                                )
                            }
                        >
                            {tool.label}
                        </Link>
                    ))}


                    <Link
                        to="/"
                        className="insight-chip insight-chip-button"
                    >
                        К анализу видео
                    </Link>
                </div>
            </nav>


            <Outlet />
        </main>
    );
}
