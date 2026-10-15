import { NavLink, Outlet } from 'react-router';
import { t } from '../../i18n/es';

export function Layout() {
  return (
    <div className="fr-shell">
      <a href="#main" className="fr-shell-skip">
        {t('a11y.skip')}
      </a>
      <nav aria-label={t('nav.main')} className="fr-shell-nav">
        <ul>
          <li>
            <NavLink to="/">{t('nav.today')}</NavLink>
          </li>
          <li>
            <NavLink to="/classroom">{t('nav.classroom')}</NavLink>
          </li>
          <li>
            <NavLink to="/review">{t('nav.review')}</NavLink>
          </li>
          <li>
            <NavLink to="/cards">{t('nav.cards')}</NavLink>
          </li>
          <li>
            <NavLink to="/progress">{t('nav.progress')}</NavLink>
          </li>
          <li>
            <NavLink to="/settings">{t('nav.settings')}</NavLink>
          </li>
        </ul>
      </nav>
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}

export default Layout;
