import { Link } from "react-router-dom";


const TOOLS = [
    {
        to: "/dev/vision",
        title: "Визуальный анализ кадра",
        text: (
            "Метрики, гео-улики Grounding DINO + SAM2, SegFormer, "
            + "лица и тайминги на одном изображении."
        ),
    },
    {
        to: "/dev/video-lab",
        title: "Видео-лаб",
        text: (
            "Загрузить видео, выбрать таймкод и прогнать выбранные "
            + "визуальные функции на кадре."
        ),
    },
    {
        to: "/dev/odometry",
        title: "Одометрия и BEV",
        text: (
            "ORB + essential matrix по кадрам, диагностика пар и "
            + "anchor-BEV: маршрут и только сильные ориентиры."
        ),
    },
    {
        to: "/dev/map",
        title: "Карт-исследование",
        text: (
            "Регион по растительности, слои OSM/Wikimapia/Генштаб/"
            + "кадастр/спутник, солнце, тени и триангуляция."
        ),
    },
    {
        to: "/dev/chat",
        title: "AI API чат",
        text: "Проверка внешнего текстового провайдера.",
    },
];


export default function DevHomePage() {
    return (
        <section className="panel">
            <h1>Тестовые инструменты</h1>


            <p className="muted">
                Выберите инструмент для проверки сервисов. Каждая
                страница работает независимо от заданий и полного
                pipeline.
            </p>


            <div className="dev-grid">
                {TOOLS.map((tool) => (
                    <article key={tool.to} className="dev-card">
                        <h3>{tool.title}</h3>

                        <p className="muted">{tool.text}</p>

                        <Link
                            to={tool.to}
                            className="insight-chip insight-chip-button"
                        >
                            Открыть
                        </Link>
                    </article>
                ))}
            </div>
        </section>
    );
}
