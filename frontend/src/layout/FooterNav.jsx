import { useEffect, useMemo, useState } from "react";

function scrollToSection(id) {
    const node = document.getElementById(id);
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "start" });
}

function scrollToTop() {
    window.scrollTo({ top: 0, behavior: "smooth" });
}

export default function FooterNav({ sections = [] }) {
    const items = useMemo(
        () => sections.filter((item) => item?.id && item?.label),
        [sections],
    );
    const [active, setActive] = useState(items[0]?.id || "");

    useEffect(() => {
        if (!items.length) return undefined;

        const observer = new IntersectionObserver(
            (entries) => {
                const visible = entries
                    .filter((entry) => entry.isIntersecting)
                    .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
                if (visible?.target?.id) {
                    setActive(visible.target.id);
                }
            },
            {
                root: null,
                rootMargin: "-18% 0px -62% 0px",
                threshold: [0.08, 0.25, 0.5, 0.75],
            },
        );

        items.forEach((item) => {
            const node = document.getElementById(item.id);
            if (node) observer.observe(node);
        });

        return () => observer.disconnect();
    }, [items]);

    if (!items.length) return null;

    return (
        <nav className="footer-nav" aria-label="Навигация по разделам анализа">
            <div className="footer-nav__inner">
                {items.map((item) => (
                    <button
                        key={item.id}
                        type="button"
                        className={`footer-nav__item ${active === item.id ? "is-active" : ""}`}
                        onClick={() => scrollToSection(item.id)}
                    >
                        {item.label}
                    </button>
                ))}

                <button
                    type="button"
                    className="footer-nav__item footer-nav__item--top"
                    onClick={scrollToTop}
                    title="Вернуться к началу страницы"
                >
                    ↑ Наверх
                </button>
            </div>
        </nav>
    );
}
