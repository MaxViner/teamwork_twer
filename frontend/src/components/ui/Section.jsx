/**
 * Якорный блок раздела: нужен для навигации внизу страницы.
 *
 * Пустой раздел скрывается через CSS (.section-anchor-wrap:empty),
 * поэтому панели можно рендерить условно без пустых пропусков.
 */
export function Section({ id, children }) {
    return (
        <section id={id} className="section-anchor-wrap">
            {children}
        </section>
    );
}


export default Section;
