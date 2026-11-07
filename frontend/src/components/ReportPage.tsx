import React, { useCallback, useState } from 'react';
import { useKeycloak } from '@react-keycloak/web';

// Shape of GET /reports from the reports API (see reports-api/app/service.py).
interface ReportDay {
  report_date: string;
  prosthesis_serial: string;
  model: string;
  side: string;
  actions_count: number;
  avg_reaction_ms: number;
  p95_reaction_ms: number;
  max_reaction_ms: number;
  slow_actions_count: number;
  avg_noise_level: number;
  avg_battery_pct: number;
  min_battery_pct: number;
  error_count: number;
  active_hours: number;
  partial: boolean;
}

interface Report {
  user: { id: string; username: string; full_name: string };
  period: { from: string; to: string; requested_to: string; clamped: boolean };
  data_processed_until: string;
  generated_at: string;
  summary: {
    days: number;
    prostheses: string[];
    actions_count: number;
    avg_reaction_ms: number | null;
    max_reaction_ms: number | null;
    slow_actions_share: number | null;
    avg_noise_level: number | null;
    min_battery_pct: number | null;
    error_count: number;
  };
  days: ReportDay[];
}

const API_URL = process.env.REACT_APP_API_URL;

const isoDate = (d: Date) => d.toISOString().slice(0, 10);
const daysAgo = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoDate(d);
};

const ReportPage: React.FC = () => {
  const { keycloak, initialized } = useKeycloak();
  const [from, setFrom] = useState(daysAgo(6));
  const [to, setTo] = useState(daysAgo(0));
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Calls the reports API with the current access token (refreshed first if it is about to expire).
  const callReportsApi = useCallback(async (format: 'json' | 'csv') => {
    await keycloak.updateToken(30);
    const params = new URLSearchParams({ from, to, format });
    const response = await fetch(`${API_URL}/reports?${params}`, {
      headers: { Authorization: `Bearer ${keycloak.token}` },
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (body.detail) detail = body.detail;
        if (body.data_processed_until) detail += ` (data processed until ${new Date(body.data_processed_until).toLocaleString()})`;
      } catch {
        // non-JSON error body: keep the status text
      }
      if (response.status === 401) detail = 'Session expired or token rejected. Please log in again.';
      throw new Error(detail);
    }
    return response;
  }, [keycloak, from, to]);

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await callReportsApi('json');
      setReport(await response.json());
    } catch (err) {
      setReport(null);
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const downloadCsv = async () => {
    setDownloading(true);
    setError(null);
    try {
      const response = await callReportsApi('csv');
      const blob = await response.blob();
      const disposition = response.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = match ? match[1] : `bionicpro-report-${from}-${to}.csv`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setDownloading(false);
    }
  };

  if (!initialized) {
    return <div className="flex items-center justify-center min-h-screen bg-gray-100">Loading...</div>;
  }

  if (!keycloak.authenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <h1 className="text-2xl font-bold mb-6">BionicPRO · Prosthesis usage reports</h1>
        <button
          onClick={() => keycloak.login()}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </button>
      </div>
    );
  }

  const username = (keycloak.tokenParsed as { preferred_username?: string } | undefined)?.preferred_username;
  const busy = loading || downloading;

  return (
    <div className="min-h-screen bg-gray-100 py-10 px-4">
      <div className="max-w-5xl mx-auto bg-white rounded-lg shadow-md p-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Usage Reports</h1>
          <div className="text-sm text-gray-600">
            {username}
            <button onClick={() => keycloak.logout()} className="ml-4 px-3 py-1 border rounded hover:bg-gray-50">
              Logout
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-4 mb-6">
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">From</span>
            <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className="border rounded px-2 py-1" />
          </label>
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">To</span>
            <input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} className="border rounded px-2 py-1" />
          </label>
          <button
            onClick={loadReport}
            disabled={busy}
            className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${busy ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {loading ? 'Generating Report...' : 'Get Report'}
          </button>
          <button
            onClick={downloadCsv}
            disabled={busy}
            className={`px-4 py-2 border border-blue-500 text-blue-600 rounded hover:bg-blue-50 ${busy ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {downloading ? 'Preparing CSV...' : 'Download CSV'}
          </button>
        </div>

        {error && <div className="mb-6 p-4 bg-red-100 text-red-700 rounded">{error}</div>}

        {report && (
          <>
            <div className="mb-4 text-sm text-gray-600">
              Report for <b>{report.user.full_name}</b> ({report.user.username}), {report.period.from} – {report.period.to}.
              Data processed until {new Date(report.data_processed_until).toLocaleString()}.
              {report.period.clamped && (
                <span className="ml-1 text-amber-700">
                  The requested end date {report.period.requested_to} is not processed yet, the report is limited to the processed period.
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6 text-sm">
              <Stat label="Actions" value={report.summary.actions_count} />
              <Stat label="Avg reaction, ms" value={report.summary.avg_reaction_ms ?? '—'} />
              <Stat label="Slow actions (>100 ms)" value={report.summary.slow_actions_share == null ? '—' : `${(report.summary.slow_actions_share * 100).toFixed(1)}%`} />
              <Stat label="Avg myo noise" value={report.summary.avg_noise_level ?? '—'} />
              <Stat label="Min battery, %" value={report.summary.min_battery_pct ?? '—'} />
              <Stat label="Errors" value={report.summary.error_count} />
              <Stat label="Days" value={report.summary.days} />
              <Stat label="Prostheses" value={report.summary.prostheses.join(', ') || '—'} />
            </div>

            {report.days.length === 0 ? (
              <div className="text-gray-500">No telemetry for this period.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 text-left">
                      <th className="p-2">Date</th>
                      <th className="p-2">Prosthesis</th>
                      <th className="p-2 text-right">Actions</th>
                      <th className="p-2 text-right">Avg ms</th>
                      <th className="p-2 text-right">p95 ms</th>
                      <th className="p-2 text-right">Slow</th>
                      <th className="p-2 text-right">Noise</th>
                      <th className="p-2 text-right">Battery avg/min</th>
                      <th className="p-2 text-right">Errors</th>
                      <th className="p-2 text-right">Active h</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.days.map((d) => (
                      <tr key={`${d.report_date}-${d.prosthesis_serial}`} className="border-t">
                        <td className="p-2 whitespace-nowrap">
                          {d.report_date}
                          {d.partial && <span className="ml-1 text-xs text-amber-700" title="Day not complete yet">(partial)</span>}
                        </td>
                        <td className="p-2 whitespace-nowrap">{d.prosthesis_serial} <span className="text-gray-500">{d.model}, {d.side}</span></td>
                        <td className="p-2 text-right">{d.actions_count}</td>
                        <td className="p-2 text-right">{d.avg_reaction_ms.toFixed(1)}</td>
                        <td className="p-2 text-right">{d.p95_reaction_ms}</td>
                        <td className="p-2 text-right">{d.slow_actions_count}</td>
                        <td className="p-2 text-right">{d.avg_noise_level.toFixed(3)}</td>
                        <td className="p-2 text-right">{d.avg_battery_pct.toFixed(0)} / {d.min_battery_pct}</td>
                        <td className="p-2 text-right">{d.error_count}</td>
                        <td className="p-2 text-right">{d.active_hours}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

const Stat: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="p-3 bg-gray-50 rounded">
    <div className="text-gray-500">{label}</div>
    <div className="text-lg font-semibold">{value}</div>
  </div>
);

export default ReportPage;
