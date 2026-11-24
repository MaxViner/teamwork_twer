import { Link, Outlet } from "react-router-dom";
import PageHeader from "../layout/PageHeader.jsx";


export default function DevLayout() {
    return (
        <main className="app">
            <PageHeader />


            <nav className="panel">
                <h2>Тестовые инструменты</h2>


                <div className="insight-chips">
                    <Link
                        to="/dev/vision"
                        className="insight-chip insight-chip-button"
                    >
                        Распознавание изображения
                    </Link>


                    <Link
                        to="/dev/chat"
                        className="insight-chip insight-chip-button"
                    >
                        AI API чат
                    </Link>


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