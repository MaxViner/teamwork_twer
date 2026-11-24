import { Link } from "react-router-dom";


export default function NotFoundPage() {
    return (
        <main className="app">
            <section className="panel">
                <h1>Страница не найдена</h1>


                <p className="muted">
                    Проверьте адрес или вернитесь к анализу видео.
                </p>


                <Link to="/" className="button-link">
                    К анализу видео
                </Link>
            </section>
        </main>
    );
}