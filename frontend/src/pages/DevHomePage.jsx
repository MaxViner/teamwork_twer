import { Link } from "react-router-dom";


export default function DevHomePage() {
    return (
        <main className="app">
            <section className="panel">
                <h1>Тестовые инструменты</h1>


                <p className="muted">
                    Выберите инструмент для проверки сервисов.
                </p>


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
                </div>
            </section>
        </main>
    );
}