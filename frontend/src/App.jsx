import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { USE_MOCKS } from './services/api.js';
import OverviewPage from './pages/OverviewPage.jsx';
import MediaInvestigationPage from './pages/MediaInvestigationPage.jsx';
import CampaignAnalysisPage from './pages/CampaignAnalysisPage.jsx';
import DisseminationPage from './pages/DisseminationPage.jsx';
import ReportPage from './pages/ReportPage.jsx';

const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/media', label: 'Media' },
  { to: '/campaigns', label: 'Campaigns' },
  { to: '/dissemination', label: 'Dissemination' },
  { to: '/reports', label: 'Reports' },
];

export default function App() {
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand">
            <img src="/favicon.svg" width="26" height="26" alt="" />
            <span>
              Veritas <span className="brand-accent">AI</span>
            </span>
          </Link>
          <nav aria-label="Main">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className="nav-link">
                {item.label}
              </NavLink>
            ))}
          </nav>
          <Link to="/campaigns" className="button button-primary topbar-action">
            Import posts
          </Link>
        </div>
        {USE_MOCKS && (
          <div className="mock-banner" role="status">
            <strong>Labeled campaign samples.</strong> Media analysis and investigation reports stay disabled. They are not filled with sample scores.
          </div>
        )}
      </header>

      <main className="main">
        <div className="content">
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/media" element={<MediaInvestigationPage />} />
            <Route path="/campaigns/:campaignId?" element={<CampaignAnalysisPage />} />
            <Route path="/dissemination/:caseId?" element={<DisseminationPage />} />
            <Route path="/reports/:reportId?" element={<ReportPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>

      <footer className="footer">Prototype. Findings support human review and are not conclusions.</footer>
    </div>
  );
}
