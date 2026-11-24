import { useState } from "react";
import { sendChat } from "../../api/dev.js";


export default function AiChatTestPanel() {
    const [message, setMessage] = useState("");
    const [webSearch, setWebSearch] = useState(false);
    const [messages, setMessages] = useState([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");


    const handleSend = async () => {
        const text = message.trim();

        if (!text || busy) return;

        const userMessage = {
            role: "user",
            text,
        };

        setMessages((current) => [
            ...current,
            userMessage,
        ]);

        setMessage("");
        setBusy(true);
        setError("");

        try {
            const response = await sendChat(text, {
                webSearch,
            });

            setMessages((current) => [
                ...current,
                {
                    role: "assistant",
                    text: response.answer,
                    sources: response.sources || [],
                },
            ]);

        } catch (err) {
            setError(err.message);

        } finally {
            setBusy(false);
        }
    };


    return (
        <section className="panel">
            <h2>Тест AI API</h2>

            <p className="muted">
                Проверка текстового чата с настроенным AI-провайдером.
            </p>

            <div>
                {messages.map((item, index) => (
                    <div
                        key={index}
                        className="insight-overview"
                    >
                        <strong>
                            {item.role === "user"
                                ? "Вы"
                                : "AI"}
                        </strong>

                        <p>{item.text}</p>

                        {item.sources?.length > 0 && (
                            <ul>
                                {item.sources.map((
                                    source,
                                    sourceIndex
                                ) => (
                                    <li key={sourceIndex}>
                                        <a
                                            href={source.url}
                                            target="_blank"
                                            rel="noreferrer"
                                        >
                                            {source.title}
                                        </a>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                ))}
            </div>

            <label>
                <input
                    type="checkbox"
                    checked={webSearch}
                    onChange={(event) => (
                        setWebSearch(event.target.checked)
                    )}
                />
                Включить поиск в интернете
            </label>

            <textarea
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder="Задайте вопрос модели"
            />

            <button
                className="primary"
                disabled={busy || !message.trim()}
                onClick={handleSend}
            >
                {busy ? "Отправляю…" : "Отправить"}
            </button>

            {error && (
                <div className="error">{error}</div>
            )}
        </section>
    );
}